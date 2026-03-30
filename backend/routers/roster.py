import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database import get_db
from models.player import Player
from models.roster import MyRoster
from models.user import User, UserLeague
from services.sleeper_service import (
    get_user_id,
    get_eligible_leagues,
    get_roster,
    get_all_players,
    CURRENT_SEASON,
)

router = APIRouter()
logger = logging.getLogger(__name__)

RELEVANT_POSITIONS = {"QB", "RB", "WR", "TE", "K"}


@router.get("/leagues")
async def list_eligible_leagues(
    sleeper_username: str = Query(..., description="Sleeper username"),
):
    """
    Returns the user's redraft PPR leagues from Sleeper.
    Used in Settings to let the user pick which league to track.
    """
    user_id = await get_user_id(sleeper_username)
    if not user_id:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")

    leagues = await get_eligible_leagues(user_id)
    if not leagues:
        return {
            "leagues": [],
            "message": "No redraft PPR leagues found for this Sleeper account.",
        }

    return {"leagues": leagues, "sleeper_user_id": user_id}


@router.get("/roster")
async def get_my_roster(
    sleeper_username: str = Query(..., description="Sleeper username"),
    league_id: str = Query(..., description="Sleeper league ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetches the user's roster from Sleeper, syncs players + roster into Neon,
    and returns the full roster with player details.
    """
    # Resolve username → user_id
    sleeper_user_id = await get_user_id(sleeper_username)
    if not sleeper_user_id:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")

    # Validate this is a redraft PPR league owned by this user
    eligible = await get_eligible_leagues(sleeper_user_id)
    eligible_ids = {l["league_id"] for l in eligible}
    if league_id not in eligible_ids:
        raise HTTPException(
            status_code=400,
            detail="League is not a redraft PPR league or does not belong to this user."
        )

    # Fetch roster from Sleeper
    roster = await get_roster(league_id, sleeper_user_id)
    if not roster:
        raise HTTPException(status_code=404, detail="Roster not found in this league.")

    player_ids: list[str] = roster.get("players") or []
    starters: set[str] = set(roster.get("starters") or [])

    if not player_ids:
        return {"roster": [], "source": "sleeper", "warning": "Roster appears empty."}

    # Fetch full player map from Sleeper to get names/positions
    all_players = await get_all_players()

    # --- Upsert players into `players` table ---
    players_to_upsert = []
    for pid in player_ids:
        p = all_players.get(pid, {})
        position = p.get("position", "")
        if position not in RELEVANT_POSITIONS:
            continue
        # Sleeper returns espn_id as int — cast to str for VARCHAR column
        espn_id = p.get("espn_id")
        espn_id_str = str(espn_id) if espn_id is not None else None
        players_to_upsert.append({
            "player_id": pid,
            "name": _full_name(p),
            "position": position,
            "nfl_team": p.get("team") or p.get("nfl_team"),
            "sleeper_id": pid,
            "espn_id": espn_id_str,
            "espn_athlete_id": espn_id_str,
            "injury_status": p.get("injury_status", "Active"),
        })

    if players_to_upsert:
        stmt = pg_insert(Player).values(players_to_upsert)
        stmt = stmt.on_conflict_do_update(
            index_elements=["player_id"],
            set_={
                "name": stmt.excluded.name,
                "position": stmt.excluded.position,
                "nfl_team": stmt.excluded.nfl_team,
                "espn_id": stmt.excluded.espn_id,
                "injury_status": stmt.excluded.injury_status,
            },
        )
        await db.execute(stmt)

    # --- Ensure placeholder user exists (replaced with real Clerk auth in Phase 5) ---
    PLACEHOLDER_USER_ID = 1
    existing_user = await db.get(User, PLACEHOLDER_USER_ID)
    if not existing_user:
        db.add(User(
            id=PLACEHOLDER_USER_ID,
            clerk_id="placeholder",
            email="placeholder@fantas.ai",
            username=sleeper_username,
            is_approved=True,
            sleeper_username=sleeper_username,
            sleeper_user_id=sleeper_user_id,
        ))
        await db.flush()

    # --- Upsert this league into user_leagues and mark as primary ---
    from sqlalchemy import select
    result = await db.execute(
        select(UserLeague).where(
            UserLeague.user_id == PLACEHOLDER_USER_ID,
            UserLeague.league_id == league_id,
            UserLeague.platform == "SLEEPER",
        )
    )
    existing_league = result.scalar_one_or_none()
    if not existing_league:
        # Clear any existing primary flag before setting new one
        await db.execute(
            select(UserLeague).where(UserLeague.user_id == PLACEHOLDER_USER_ID)
        )
        db.add(UserLeague(
            user_id=PLACEHOLDER_USER_ID,
            platform="SLEEPER",
            league_id=league_id,
            league_name=next((l["name"] for l in eligible if l["league_id"] == league_id), None),
            total_rosters=next((l.get("total_rosters") for l in eligible if l["league_id"] == league_id), None),
            season=CURRENT_SEASON,
            is_primary=True,
        ))
        await db.flush()

    # --- Clear old roster and re-sync ---
    await db.execute(
        delete(MyRoster).where(MyRoster.user_id == PLACEHOLDER_USER_ID)
    )

    valid_pids = {p["player_id"] for p in players_to_upsert}
    for pid in player_ids:
        if pid not in valid_pids:
            continue
        db.add(MyRoster(
            user_id=PLACEHOLDER_USER_ID,
            player_id=pid,
            is_starter=pid in starters,
            slot=_guess_slot(pid, starters, all_players),
            acquisition_date=date.today(),
        ))

    await db.commit()

    # --- Build response ---
    roster_out = []
    for pid in player_ids:
        p = all_players.get(pid, {})
        position = p.get("position", "")
        if position not in RELEVANT_POSITIONS:
            continue
        roster_out.append({
            "player_id": pid,
            "name": _full_name(p),
            "position": position,
            "nfl_team": p.get("team") or p.get("nfl_team"),
            "injury_status": p.get("injury_status", "Active"),
            "is_starter": pid in starters,
            "slot": _guess_slot(pid, starters, all_players),
        })

    position_order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4}
    roster_out.sort(key=lambda x: (0 if x["is_starter"] else 1, position_order.get(x["position"], 9)))

    return {
        "roster": roster_out,
        "total_players": len(roster_out),
        "starters": len([p for p in roster_out if p["is_starter"]]),
        "source": "sleeper",
        "season": CURRENT_SEASON,
        "league_id": league_id,
    }


def _full_name(player: dict) -> str:
    first = player.get("first_name", "")
    last = player.get("last_name", "")
    return f"{first} {last}".strip() or player.get("full_name", "Unknown")


def _guess_slot(pid: str, starters: set, all_players: dict) -> str:
    """Best-effort slot label based on position. Exact slots come from ESPN in Phase 2."""
    if pid not in starters:
        return "BN"
    p = all_players.get(pid, {})
    return p.get("position", "BN")
