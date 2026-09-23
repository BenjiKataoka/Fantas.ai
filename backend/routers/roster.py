import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserLeague
from services.sleeper_service import get_eligible_leagues
from auth import get_current_user
from services import tracker_service
from services import espn_service
from services.league_service import (RELEVANT_POSITIONS, all_leagues, espn_leagues as _espn_leagues, full_name,
                                     resolve_sleeper_user_id,
                                     get_or_create_user_league,
                                     league_season as _resolve_league_season, sync_espn_league,
                                     sync_sleeper_league)
from services.projection_service import get_nfl_state

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/leagues")
async def list_eligible_leagues(
    sleeper_username: str | None = Query(None, description="Sleeper username; not needed for ESPN-only users"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    The user's redraft PPR leagues across platforms: Sleeper by username, plus ESPN when
    the user has saved ESPN cookies. Each entry carries its `platform`.
    """
    user_id = await resolve_sleeper_user_id(user, sleeper_username)
    if sleeper_username and not user_id:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")

    nfl_state = await get_nfl_state()
    league_season = _resolve_league_season(nfl_state)
    leagues = await all_leagues(user, user_id, league_season, db)
    if not leagues:
        return {
            "leagues": [],
            "message": ("No redraft PPR leagues found for this Sleeper account." if user_id
                        else "Connect Sleeper or ESPN to see your leagues."),
        }

    return {"leagues": leagues, "sleeper_user_id": user_id}


class EspnLookup(BaseModel):
    league: str   # a pasted league link or a bare league id


class EspnPublicConnect(BaseModel):
    league_id: str
    team_id: int


async def _public_espn_league(league_id: str, season: int) -> dict:
    """Fetch a league without cookies and check it's usable, or raise a clear 400."""
    try:
        league = await espn_service.get_espn_league(league_id, season)
    except espn_service.EspnAuthError:
        raise HTTPException(status_code=400, detail="That league is private. Connect your ESPN account below to add it.")
    if not league:
        raise HTTPException(status_code=404, detail=f"No ESPN league {league_id} found for the {season} season.")
    if not espn_service.espn_is_redraft_ppr(league):
        raise HTTPException(status_code=400, detail="Only redraft PPR leagues are supported.")
    return league


@router.post("/leagues/espn/lookup")
async def lookup_espn_league(body: EspnLookup, user: User = Depends(get_current_user)):
    """Step 1 of adding a public ESPN league: resolve the link and list its teams to pick from."""
    league_id = espn_service.parse_espn_league_id(body.league)
    if not league_id:
        raise HTTPException(status_code=400, detail="Paste a league link like fantasy.espn.com/football/league?leagueId=123456.")
    season = _resolve_league_season(await get_nfl_state())
    league = await _public_espn_league(league_id, season)
    return {"league_id": league_id, "name": (league.get("settings") or {}).get("name"),
            "teams": espn_service.espn_teams(league)}


@router.post("/leagues/espn/public")
async def connect_public_espn_league(
    body: EspnPublicConnect,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Step 2: save the league with the team the user picked."""
    season = _resolve_league_season(await get_nfl_state())
    league = await _public_espn_league(body.league_id, season)
    if not espn_service.espn_my_team(league, team_id=body.team_id):
        raise HTTPException(status_code=400, detail="That team isn't in this league.")
    settings_ = league.get("settings") or {}
    ul = await get_or_create_user_league(db, user.id, "ESPN", body.league_id)
    ul.league_name, ul.total_rosters, ul.season, ul.team_id = settings_.get("name"), settings_.get("size"), season, body.team_id
    return {"league_id": body.league_id, "name": ul.league_name, "platform": "ESPN", "public": True}


@router.delete("/leagues/espn/{league_id}")
async def remove_espn_league(league_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Remove a public ESPN league (its roster rows go with it via the cascade)."""
    await db.execute(delete(UserLeague).where(
        UserLeague.user_id == user.id, UserLeague.platform == "ESPN", UserLeague.league_id == league_id,
    ))
    return {"removed": league_id}


@router.get("/roster")
async def get_my_roster(
    sleeper_username: str | None = Query(None, description="Sleeper username; not needed for ESPN leagues"),
    league_id: str = Query(..., description="League ID on its platform"),
    platform: str = Query("SLEEPER", pattern="^(SLEEPER|ESPN)$"),
    force: bool = Query(False, description="Skip the 15-minute league cache (manual refresh)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetches the user's roster from Sleeper or ESPN, syncs players + roster into Neon,
    and returns the full roster with player details.
    """
    # Fetch NFL state first, used for season/week throughout this handler
    nfl_state = await get_nfl_state()

    # Resolve username → user_id (ESPN leagues don't need one)
    sleeper_user_id = await resolve_sleeper_user_id(user, sleeper_username)
    if platform == "SLEEPER" and not sleeper_user_id:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")

    # Validate this is a redraft PPR league owned by this user.
    # Uses the same season resolution as /api/leagues so the dropdown and this
    # validation always agree (see _resolve_league_season).
    league_season = _resolve_league_season(nfl_state)
    eligible = (await _espn_leagues(user, league_season, db) if platform == "ESPN"
                else await get_eligible_leagues(sleeper_user_id, season=league_season))
    eligible_ids = {l["league_id"] for l in eligible}
    if league_id not in eligible_ids and user.espn_needs_reconnect and platform == "ESPN":
        # The ESPN lookup above hit rejected cookies (and set the flag): say so, and commit
        # the flag before raising, since the error response would roll it back.
        await db.commit()
        raise HTTPException(status_code=401, detail="Your ESPN cookies expired. Paste fresh ones in Settings.")
    if league_id not in eligible_ids:
        raise HTTPException(
            status_code=400,
            detail="League is not a redraft PPR league or does not belong to this user."
        )

    # --- Persist the Sleeper credentials on the authenticated user ---
    if sleeper_username:
        user.sleeper_username = sleeper_username
    user.sleeper_user_id = user.sleeper_user_id or sleeper_user_id

    # --- Upsert this league into user_leagues and make it the primary (last loaded) ---
    meta = next(l for l in eligible if l["league_id"] == league_id)
    ul = await get_or_create_user_league(db, user.id, platform, league_id, league_name=meta["name"],
                                         total_rosters=meta.get("total_rosters"), season=league_season)
    await db.execute(
        update(UserLeague).where(UserLeague.user_id == user.id).values(is_primary=(UserLeague.id == ul.id))
    )

    try:
        synced = (await sync_espn_league(db, user, ul, nfl_state, force=force) if platform == "ESPN"
                  else await sync_sleeper_league(db, user, sleeper_user_id, ul, nfl_state, force=force))
    except espn_service.EspnAuthError:
        # Commit the flag before raising: the error response would otherwise roll it back.
        user.espn_needs_reconnect = True
        await db.commit()
        raise HTTPException(status_code=401, detail="Your ESPN cookies expired. Paste fresh ones in Settings.")
    if synced is None:
        raise HTTPException(status_code=404, detail="Roster not found in this league.")
    player_ids, starters, slots = synced["player_ids"], synced["starters"], synced["slots"]
    all_players, projections = synced["all_players"], synced["projections"]
    if not player_ids:
        return {"roster": [], "source": "sleeper", "warning": "Roster appears empty."}

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
            "name": full_name(p),
            "position": position,
            "nfl_team": p.get("team") or p.get("nfl_team"),
            "injury_status": p.get("injury_status", "Active"),
            "is_starter": pid in starters,
            "slot": slots.get(pid, "BN"),
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
        "source": platform.lower(),
        "platform": platform,
        "season": nfl_state["season"],
        "week": nfl_state["week"],
        "season_type": nfl_state["season_type"],
        "league_id": league_id,
    }
