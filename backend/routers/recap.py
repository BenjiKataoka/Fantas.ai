"""GET /api/recap/{week}: actual points vs. projections for your roster in one league."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.player import Player
from models.projection import Projection
from models.user import User
from services import sleeper_service
from services.projection_service import get_nfl_state
from services.league_service import espn_team_id, resolve_sleeper_user_id
from services.recap_service import build_recap, find_matchup

router = APIRouter()
logger = logging.getLogger(__name__)


async def _espn_week(league_id: str, user: User, season: int, week: int, final: bool, db: AsyncSession):
    """An ESPN week reshaped into the Sleeper-style matchup build_recap already reads:
    the week's box score carries each player's points and lineup slot."""
    from services import espn_service

    team_id = await espn_team_id(db, user.id, league_id)
    try:
        data = await espn_service.get_espn_boxscore(league_id, season, week, user.espn_s2, user.swid, live=not final)
    except espn_service.EspnAuthError:
        raise HTTPException(status_code=401, detail="Your ESPN cookies expired. Paste fresh ones in Settings.")
    me = espn_service.espn_my_team(data or {}, swid=user.swid, team_id=team_id)
    if not me:
        raise HTTPException(status_code=404, detail="You don't have a team in this league.")
    game = next((g for g in (data.get("schedule") or []) if g.get("matchupPeriodId") == week
                 and me["id"] in ((g.get("home") or {}).get("teamId"), (g.get("away") or {}).get("teamId"))), None)
    if not game:
        raise HTTPException(status_code=502, detail=f"ESPN has no week {week} matchup for your team.")
    side = game["home"] if game["home"]["teamId"] == me["id"] else game["away"]
    entries = (side.get("rosterForCurrentScoringPeriod") or {}).get("entries") or []

    all_players = await sleeper_service.get_all_players()
    starters, players, points = [], [], {}
    for pid, e in espn_service.espn_to_sleeper_ids(entries, all_players):
        players.append(pid)
        points[pid] = (e.get("playerPoolEntry") or {}).get("appliedStatTotal") or 0.0
        if e.get("lineupSlotId") in espn_service.ESPN_TO_SLOT:
            starters.append(pid)
    matchup = {"starters": starters, "players": players, "players_points": points,
               "points": side.get("totalPoints") or 0.0}
    return matchup, espn_service.espn_roster_positions(data or {}), ((data or {}).get("settings") or {}).get("name")


@router.get("/recap/{week}")
async def get_recap(
    week: int,
    sleeper_username: str | None = Query(None, description="Sleeper username; not needed for ESPN leagues"),
    league_id: str = Query(..., description="League ID on its platform"),
    platform: str = Query("SLEEPER", pattern="^(SLEEPER|ESPN)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    state = await get_nfl_state()
    season, current_week = state["season"], state["week"]
    if state.get("season_type") == "off":
        raise HTTPException(status_code=400, detail="Recaps are only available during the season.")
    if week < 1 or week > current_week:
        raise HTTPException(status_code=400, detail=f"Week {week} hasn't been played yet.")
    final = week < current_week  # Sleeper advances the week after Monday night

    if platform == "ESPN":
        matchup, slots, league_name = await _espn_week(league_id, user, season, week, final, db)
    else:
        sleeper_user_id = await resolve_sleeper_user_id(user, sleeper_username)
        if not sleeper_user_id:
            raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")

        league, roster, matchups = await asyncio.gather(
            sleeper_service.get_league(league_id),
            sleeper_service.get_roster(league_id, sleeper_user_id),
            sleeper_service.get_matchups(league_id, week, live=not final),
        )
        if not roster:
            raise HTTPException(status_code=404, detail="You don't have a roster in this league.")
        matchup = find_matchup(matchups, roster["roster_id"])
        if not matchup:
            raise HTTPException(status_code=502, detail="Sleeper returned no matchup for this week.")
        slots, league_name = (league or {}).get("roster_positions") or [], (league or {}).get("name")

    pids = [p for p in matchup.get("players") or [] if p]
    proj_rows = (await db.execute(
        select(Projection).where(Projection.player_id.in_(pids), Projection.week == week, Projection.season == season)
    )).scalars().all()
    projections = {
        r.player_id: {"sleeper": r.sleeper_proj, "espn": r.espn_proj, "fp": r.fp_proj, "weighted": r.weighted_proj}
        for r in proj_rows
    }

    info = {
        p.player_id: {"name": p.name, "position": p.position, "nfl_team": p.nfl_team}
        for p in (await db.execute(select(Player).where(Player.player_id.in_(pids)))).scalars().all()
    }
    missing = [p for p in pids if p not in info and not p.isalpha()]  # alpha ids are team defenses
    if missing:  # picked up since the last roster sync; Sleeper's player map is cached 24h
        all_players = await sleeper_service.get_all_players()
        for pid in missing:
            sp = all_players.get(pid) or {}
            info[pid] = {"name": sp.get("full_name") or pid, "position": sp.get("position") or "?", "nfl_team": sp.get("team")}

    recap = build_recap(matchup, slots, projections, info, week, season, final)
    recap["league_name"] = league_name
    if not projections:
        recap["warning"] = f"No saved projections for Week {week}. The app only saves them when your roster is loaded that week."
    return recap
