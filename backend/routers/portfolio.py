"""GET /api/portfolio: every player the user owns across all their leagues, listed once."""
import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.player import Player
from models.projection import Projection
from models.roster import MyRoster
from models.user import User, UserLeague
from services import espn_service, tracker_service
from services.league_service import all_leagues, get_or_create_user_league, league_season, resolve_sleeper_user_id, sync_league
from services.portfolio_service import build_portfolio
from services.projection_service import get_nfl_state

router = APIRouter()
logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(hours=6)  # same cadence as the scheduler's roster sync
_syncing: set[int] = set()        # user ids with a background sync in flight (per process)


async def _sync_in_background(user_id: int, league_ids: list[int], nfl_state: dict) -> None:
    """Refresh stale leagues after the response has gone out, one session per league so a
    failure can't take the others down. The page polls until this finishes."""
    from database import AsyncSessionLocal

    try:
        for ul_id in league_ids:
            async with AsyncSessionLocal() as db:
                try:
                    ul, user = await db.get(UserLeague, ul_id), await db.get(User, user_id)
                    await sync_league(db, user, ul, nfl_state)
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    logger.error(f"[Portfolio] background sync failed for user_league={ul_id}: {e}")
    finally:
        _syncing.discard(user_id)


@router.get("/portfolio")
async def get_portfolio(
    sleeper_username: str | None = Query(None, description="Sleeper username; not needed for ESPN-only users"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nfl_state = await get_nfl_state()
    season = league_season(nfl_state)
    sleeper_user_id = await resolve_sleeper_user_id(user, sleeper_username)
    user.sleeper_user_id = user.sleeper_user_id or sleeper_user_id
    eligible = await all_leagues(user, sleeper_user_id, season, db)

    # Make sure every league has a user_leagues row and a roster no older than the
    # scheduler would keep it. Each league commits on its own so one failure keeps the rest.
    # A league with no roster yet has to sync before we can show anything; a merely stale one
    # refreshes in the background so the page paints straight away.
    warnings: list[str] = []
    league_ids: list[int] = []
    stale: list[int] = []
    for l in eligible:
        ul = await get_or_create_user_league(db, user.id, l["platform"], l["league_id"], league_name=l["name"],
                                             total_rosters=l.get("total_rosters"), season=season)
        league_ids.append(ul.id)
        if ul.synced_at and datetime.utcnow() - ul.synced_at < STALE_AFTER:
            continue
        if ul.synced_at:
            stale.append(ul.id)
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

    syncing = bool(stale) and user.id not in _syncing
    if syncing:
        _syncing.add(user.id)
        asyncio.create_task(_sync_in_background(user.id, stale, nfl_state))

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
                "warnings": warnings,
                # The page polls while this is true, then shows the refreshed rosters.
                "syncing": syncing or user.id in _syncing,
                "syncing_leagues": len(stale)})
    return out
