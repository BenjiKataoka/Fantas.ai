"""GET /api/matchups: this week in every league, for the Dashboard scoreboard."""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.user import User, UserLeague
from services import espn_service, matchup_service, nfl_service, sleeper_service
from services.league_service import espn_leagues, league_season
from services.projection_engine import this_week_projection, weights_from_user
from services.projection_service import get_nfl_state

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/matchups")
async def get_matchups(
    sleeper_username: str = Query(..., description="Sleeper username"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    state = await get_nfl_state()
    if state.get("season_type") not in ("regular", "post"):
        return {"week": state.get("week"), "leagues": [], "needs": [], "kickoffs": [], "next_kickoff": None, "warnings": []}
    season, week = state["season"], state["week"]
    sleeper_user_id = await sleeper_service.get_user_id(sleeper_username)
    if not sleeper_user_id:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")

    leagues = [{**l, "platform": "SLEEPER"} for l in
               await sleeper_service.get_eligible_leagues(sleeper_user_id, season=league_season(state))]
    leagues += await espn_leagues(user, league_season(state), db)
    # Public ESPN leagues find your team by the one you picked, not by SWID.
    picked = dict((await db.execute(select(UserLeague.league_id, UserLeague.team_id).where(
        UserLeague.user_id == user.id, UserLeague.platform == "ESPN", UserLeague.team_id.isnot(None),
    ))).all())

    all_players, sleeper_proj, (espn_by_id, espn_by_name), schedule = await asyncio.gather(
        sleeper_service.get_all_players(),
        sleeper_service.get_projections(season, week),
        espn_service.get_espn_projections_full(season, week),
        nfl_service.get_week_schedule(season, week),
    )
    weights = weights_from_user(user)
    # Both sides of every matchup scored the same way (Sleeper + ESPN, your weights).
    proj = {pid: this_week_projection(all_players[pid], stats, espn_by_id, espn_by_name, weights)["weighted_proj"]
            for pid, stats in sleeper_proj.items() if pid in all_players}

    async def one(l: dict):
        try:
            if l["platform"] == "ESPN":
                return await matchup_service.espn_matchup({**l, "team_id": picked.get(l["league_id"])},
                                                         user, league_season(state), all_players, proj)
            return await matchup_service.sleeper_matchup(l, sleeper_user_id, week, all_players, proj)
        except espn_service.EspnAuthError:
            return "expired"
        except Exception as e:
            logger.error(f"[Matchups] {l['platform']} {l['league_id']} failed: {e}")
            return None

    fetched = await asyncio.gather(*(one(l) for l in leagues))

    out_leagues, needs, all_starters, warnings = [], [], [], []
    for l, m in zip(leagues, fetched):
        if m == "expired":
            warnings.append(f"{l['name']}: ESPN cookies expired.")
            continue
        if not m:
            warnings.append(f"{l['name']} couldn't load this week's matchup.")
            continue
        meta = {"league_id": l["league_id"], "platform": l["platform"], "name": l["name"], "url": m["url"]}
        issues = matchup_service.lineup_issues(meta, m["you"], m["bench"], schedule)
        you = matchup_service.team_score(m["you"], schedule)
        opp = matchup_service.team_score(m["opp"], schedule) if m["opp"] else None
        out_leagues.append({
            **meta, "record": m["record"], "opp_name": m["opp_name"], "you": you, "opp": opp,
            "win_prob": matchup_service.win_probability(you, opp) if opp is not None else None,
            "issues": sum(1 for i in issues if i["severity"] == "out"),
            "warnings": sum(1 for i in issues if i["severity"] == "warn"),
        })
        needs += issues
        all_starters += [p for p in m["you"] if p.get("player_id")]

    now = datetime.now(timezone.utc)
    upcoming = [g["kickoff"] for g in schedule.values() if g["kickoff"] > now]
    return {
        "week": week, "season": season,
        "leagues": out_leagues,
        "needs": matchup_service.group_needs(needs),
        "kickoffs": matchup_service.kickoff_windows(all_starters, schedule),
        "next_kickoff": min(upcoming).isoformat() if upcoming else None,
        "warnings": warnings,
    }
