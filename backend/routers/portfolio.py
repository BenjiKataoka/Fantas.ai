"""GET /api/portfolio: every player the user owns across all their leagues, listed once."""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.player import Player
from models.projection import Projection
from models.roster import MyRoster
from models.user import User, UserLeague
from services import espn_service, sleeper_service, tracker_service
from services.league_service import espn_leagues, get_or_create_user_league, league_season, sync_league
from services.portfolio_service import build_portfolio
from services.projection_service import get_nfl_state

router = APIRouter()
logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(hours=6)  # same cadence as the scheduler's roster sync


@router.get("/portfolio")
async def get_portfolio(
    sleeper_username: str = Query(..., description="Sleeper username"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nfl_state = await get_nfl_state()
    season = league_season(nfl_state)
    sleeper_user_id = await sleeper_service.get_user_id(sleeper_username)
    if not sleeper_user_id:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")
    user.sleeper_user_id = user.sleeper_user_id or sleeper_user_id

    eligible = [{**l, "platform": "SLEEPER"} for l in await sleeper_service.get_eligible_leagues(sleeper_user_id, season=season)]
    eligible += await espn_leagues(user, season, db)

    # Make sure every league has a user_leagues row and a roster no older than the
    # scheduler would keep it. Each league commits on its own so one failure keeps the rest.
    warnings: list[str] = []
    league_ids: list[int] = []
    for l in eligible:
        ul = await get_or_create_user_league(db, user.id, l["platform"], l["league_id"], league_name=l["name"],
                                             total_rosters=l.get("total_rosters"), season=season)
        league_ids.append(ul.id)
        if ul.synced_at and datetime.utcnow() - ul.synced_at < STALE_AFTER:
            continue
        try:
            await sync_league(db, user, ul, nfl_state)
            await db.commit()
        except espn_service.EspnAuthError:
            await db.rollback()
            await db.execute(update(User).where(User.id == user.id).values(espn_needs_reconnect=True))
            await db.commit()
            warnings.append(f"{l['name']}: ESPN cookies expired, showing its last synced roster.")
        except Exception as e:
            await db.rollback()
            logger.error(f"[Portfolio] sync failed for {l['platform']} {l['league_id']}: {e}")
            warnings.append(f"{l['name']} couldn't refresh, showing its last synced roster.")

    rows = (await db.execute(
        select(MyRoster, Player, UserLeague)
        .join(Player, Player.player_id == MyRoster.player_id)
        .join(UserLeague, UserLeague.id == MyRoster.user_league_id)
        .where(MyRoster.user_league_id.in_(league_ids))
    )).all()
    flat = [{
        "player_id": p.player_id, "name": p.name, "position": p.position, "nfl_team": p.nfl_team,
        "injury_status": p.injury_status, "is_starter": r.is_starter, "slot": r.slot,
        "league_id": ul.league_id, "platform": ul.platform, "league_name": ul.league_name,
    } for r, p, ul in rows]

    pids = list({f["player_id"] for f in flat})
    proj_rows = (await db.execute(select(Projection).where(
        Projection.player_id.in_(pids), Projection.season == nfl_state["season"], Projection.week == nfl_state["week"],
    ))).scalars().all()
    projections = {p.player_id: {"weighted_proj": p.weighted_proj, "confidence_flag": p.confidence_flag} for p in proj_rows}
    stock = await tracker_service.get_stock_profiles_for(pids, db)

    out = build_portfolio(flat, projections, stock, league_count=len(league_ids))
    out.update({"week": nfl_state["week"], "season": nfl_state["season"], "season_type": nfl_state["season_type"],
                "warnings": warnings})
    return out
