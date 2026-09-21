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
from services.recap_service import build_recap, find_matchup

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/recap/{week}")
async def get_recap(
    week: int,
    sleeper_username: str = Query(..., description="Sleeper username"),
    league_id: str = Query(..., description="Sleeper league ID"),
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

    sleeper_user_id = await sleeper_service.get_user_id(sleeper_username)
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

    recap = build_recap(matchup, (league or {}).get("roster_positions") or [], projections, info, week, season, final)
    recap["league_name"] = (league or {}).get("name")
    if not projections:
        recap["warning"] = f"No saved projections for Week {week}. The app only saves them when your roster is loaded that week."
    return recap
