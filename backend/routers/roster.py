import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.player import Player
from models.roster import MyRoster
from models.user import User, UserLeague
from services.sleeper_service import (
    get_user_id,
    get_eligible_leagues,
    get_roster,
    get_all_players,
)
from auth import get_current_user
from services import tracker_service
from services.projection_engine import weights_from_user
from services.projection_service import get_nfl_state, normalize_name, sync_projections

router = APIRouter()
logger = logging.getLogger(__name__)

RELEVANT_POSITIONS = {"QB", "RB", "WR", "TE", "K"}


def _resolve_league_season(nfl_state: dict) -> int:
    """
    The season whose Sleeper leagues we should look at.

    Sleeper always reports the upcoming season in `nfl_state` (e.g. 2026), but during
    the offseason those leagues don't exist yet — so fall back to the completed season.
    Both /api/leagues and /api/roster MUST use this so the dropdown and the roster
    validation agree on which season's leagues are eligible. Never hardcode the year.
    """
    season = nfl_state["season"]
    return season - 1 if nfl_state["season_type"] == "off" else season


@router.get("/leagues")
async def list_eligible_leagues(
    sleeper_username: str = Query(..., description="Sleeper username"),
    user: User = Depends(get_current_user),
):
    """
    Returns the user's redraft PPR leagues from Sleeper.
    Used in Settings to let the user pick which league to track.
    """
    user_id = await get_user_id(sleeper_username)
    if not user_id:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")

    nfl_state = await get_nfl_state()
    league_season = _resolve_league_season(nfl_state)
    leagues = await get_eligible_leagues(user_id, season=league_season)
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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetches the user's roster from Sleeper, syncs players + roster into Neon,
    and returns the full roster with player details.
    """
    # Fetch NFL state first — used for season/week throughout this handler
    nfl_state = await get_nfl_state()

    # Resolve username → user_id
    sleeper_user_id = await get_user_id(sleeper_username)
    if not sleeper_user_id:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")

    # Validate this is a redraft PPR league owned by this user.
    # Uses the same season resolution as /api/leagues so the dropdown and this
    # validation always agree (see _resolve_league_season).
    league_season = _resolve_league_season(nfl_state)
    eligible = await get_eligible_leagues(sleeper_user_id, season=league_season)
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

    # --- Persist the Sleeper credentials on the authenticated user ---
    user.sleeper_username = sleeper_username
    user.sleeper_user_id = sleeper_user_id

    # --- Upsert this league into user_leagues and mark as primary ---
    result = await db.execute(
        select(UserLeague).where(
            UserLeague.user_id == user.id,
            UserLeague.league_id == league_id,
            UserLeague.platform == "SLEEPER",
        )
    )
    existing_league = result.scalar_one_or_none()
    if not existing_league:
        # Clear primary flag on any existing leagues before setting the new one
        await db.execute(
            update(UserLeague)
            .where(UserLeague.user_id == user.id)
            .values(is_primary=False)
        )
        db.add(UserLeague(
            user_id=user.id,
            platform="SLEEPER",
            league_id=league_id,
            league_name=next((l["name"] for l in eligible if l["league_id"] == league_id), None),
            total_rosters=next((l.get("total_rosters") for l in eligible if l["league_id"] == league_id), None),
            season=league_season,
            is_primary=True,
        ))
        await db.flush()

    # --- Clear old roster and re-sync ---
    await db.execute(
        delete(MyRoster).where(MyRoster.user_id == user.id)
    )

    valid_pids = {p["player_id"] for p in players_to_upsert}
    for pid in player_ids:
        if pid not in valid_pids:
            continue
        db.add(MyRoster(
            user_id=user.id,
            player_id=pid,
            is_starter=pid in starters,
            slot=_guess_slot(pid, starters, all_players),
            acquisition_date=date.today(),
        ))

    # --- Sync projections if in-season ---
    projections: dict = {}
    if nfl_state["season_type"] in ("regular", "post"):
        espn_id_map = {
            p["player_id"]: p["espn_id"]
            for p in players_to_upsert
            if p.get("espn_id")
        }
        name_map = {
            p["player_id"]: normalize_name(p["name"])
            for p in players_to_upsert
        }
        # Use the authenticated user's saved weights
        user_weights = weights_from_user(user)
        projections = await sync_projections(
            player_ids=list(valid_pids),
            espn_id_map=espn_id_map,
            name_map=name_map,
            season=nfl_state["season"],
            week=nfl_state["week"],
            db=db,
            weights=user_weights,
        )

    await db.commit()

    # Current stock/sentiment profile per player (global, reused across users; absent
    # for players nobody has deep-dived yet). Powers the roster row dropdown.
    stock_map = await tracker_service.get_stock_profiles_for(player_ids, db)

    # --- Build response ---
    roster_out = []
    for pid in player_ids:
        p = all_players.get(pid, {})
        position = p.get("position", "")
        if position not in RELEVANT_POSITIONS:
            continue
        proj = projections.get(pid, {})
        roster_out.append({
            "player_id": pid,
            "name": _full_name(p),
            "position": position,
            "nfl_team": p.get("team") or p.get("nfl_team"),
            "injury_status": p.get("injury_status", "Active"),
            "is_starter": pid in starters,
            "slot": _guess_slot(pid, starters, all_players),
            "sleeper_proj": proj.get("sleeper_proj"),
            "espn_proj": proj.get("espn_proj"),
            "fp_proj": proj.get("fp_proj"),
            "weighted_proj": proj.get("weighted_proj"),
            "confidence_flag": proj.get("confidence_flag"),
            "stock": stock_map.get(pid),
        })

    position_order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4}
    roster_out.sort(key=lambda x: (0 if x["is_starter"] else 1, position_order.get(x["position"], 9)))

    return {
        "roster": roster_out,
        "total_players": len(roster_out),
        "starters": len([p for p in roster_out if p["is_starter"]]),
        "source": "sleeper",
        "season": nfl_state["season"],
        "week": nfl_state["week"],
        "season_type": nfl_state["season_type"],
        "league_id": league_id,
    }


def _full_name(player: dict) -> str:
    first = player.get("first_name", "")
    last = player.get("last_name", "")
    return f"{first} {last}".strip() or player.get("full_name", "Unknown")


def _guess_slot(pid: str, starters: set, all_players: dict) -> str:
    """Best-effort slot label based on position for Sleeper rosters."""
    if pid not in starters:
        return "BN"
    p = all_players.get(pid, {})
    return p.get("position", "BN")
