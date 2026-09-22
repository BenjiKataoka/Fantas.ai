"""GET /api/results: a finished week graded in every league, for the Dashboard's results mode."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.user import User, UserLeague
from services import espn_service, matchup_service, sleeper_service
from services.league_service import espn_leagues, league_season
from services.projection_service import get_nfl_state

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/results")
async def get_results(
    sleeper_username: str = Query(..., description="Sleeper username"),
    week: int | None = Query(None, ge=1, le=18, description="Defaults to last week"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    state = await get_nfl_state()
    week = week or state["week"] - 1
    if state.get("season_type") not in ("regular", "post") or week < 1:
        return {"week": week, "leagues": [], "record": None, "left_on_bench": 0, "misses": [], "warnings": []}
    season = league_season(state)
    sleeper_user_id = await sleeper_service.get_user_id(sleeper_username)
    if not sleeper_user_id:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")

    leagues = [{**l, "platform": "SLEEPER"} for l in await sleeper_service.get_eligible_leagues(sleeper_user_id, season=season)]
    leagues += await espn_leagues(user, season, db)
    picked = dict((await db.execute(select(UserLeague.league_id, UserLeague.team_id).where(
        UserLeague.user_id == user.id, UserLeague.platform == "ESPN", UserLeague.team_id.isnot(None),
    ))).all())
    all_players = await sleeper_service.get_all_players()

    async def one(l: dict):
        try:
            if l["platform"] == "ESPN":
                return await matchup_service.espn_week({**l, "team_id": picked.get(l["league_id"])}, user, season, week, all_players)
            return await matchup_service.sleeper_week(l, sleeper_user_id, week, all_players)
        except espn_service.EspnAuthError:
            return "expired"
        except Exception as e:
            logger.error(f"[Results] {l['platform']} {l['league_id']} week {week} failed: {e}")
            return None

    graded = await asyncio.gather(*(one(l) for l in leagues))
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
