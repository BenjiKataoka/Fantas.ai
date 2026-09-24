"""GET /api/results: a finished week graded in every league, for the Dashboard's results mode."""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.user import User
from services import matchup_service, nfl_service, sleeper_service
from services.league_service import (all_leagues, espn_team_ids, gather_per_league, league_season,
                                     resolve_sleeper_user_id)
from services.projection_service import get_nfl_state

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/results")
async def get_results(
    sleeper_username: str | None = Query(None, description="Sleeper username; not needed for ESPN-only users"),
    week: int | None = Query(None, ge=1, le=18, description="Defaults to last week"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    state = await get_nfl_state()
    # The same "is it over" question the Recap page asks. Sleeper's week does not roll
    # over until the Tuesday after Monday night, so week - 1 was a week behind for a day.
    week = week or await nfl_service.last_complete_week(state["season"], state["week"])
    if state.get("season_type") not in ("regular", "post") or week < 1:
        return {"week": week, "leagues": [], "record": None, "left_on_bench": 0, "misses": [], "warnings": []}
    season = league_season(state)
    sleeper_user_id = await resolve_sleeper_user_id(user, sleeper_username)
    leagues = await all_leagues(user, sleeper_user_id, season, db)
    picked = await espn_team_ids(db, user.id)
    all_players = await sleeper_service.get_all_players()

    graded = await gather_per_league(
        leagues,
        sleeper=lambda l: matchup_service.sleeper_week(l, sleeper_user_id, week, all_players),
        espn=lambda l: matchup_service.espn_week({**l, "team_id": picked.get(l["league_id"])},
                                                 user, season, week, all_players),
        tag=f"Results week {week}",
    )
    out, warnings = [], []
    for l, g in zip(leagues, graded):
        if g in (None, "expired"):
            warnings.append(f"{l['name']}: " + ("ESPN cookies expired." if g == "expired" else "no result for this week."))
            continue
        out.append({"league_id": l["league_id"], "platform": l["platform"], "name": l["name"], **g})

    decided = [r for r in out if r["result"]]
    misses = sorted(({**m, "league_name": r["name"]} for r in out for m in r["misses"]),
                    key=lambda m: m["points"], reverse=True)
    return {
        "week": week,
        "leagues": out,
        "record": {"wins": sum(r["result"] == "W" for r in decided), "losses": sum(r["result"] == "L" for r in decided),
                   "ties": sum(r["result"] == "T" for r in decided)},
        "left_on_bench": round(sum(r["left_on_bench"] for r in out), 1),
        "misses": misses[:5],
        "warnings": warnings,
    }
