"""
Autonomous background scheduler (APScheduler, in-process).

UTC jobs:
  - Roster sync (LLM-free, 4x daily in-season): re-pull every connected league's roster
                               and this week's projections, so nothing waits on a page load.
  - Market refresh (LLM-free): append today's ESPN rank/ADP/%rostered per tracked player.
  - Sentiment refresh (LLM):   re-analyze STALE tracked players, appending sentiment
                               history, budget/RPD-gated, paced, overlap-guarded.

Gated behind SCHEDULER_ENABLED so it never fires in tests/dev. The job functions are
independently callable (and exposed via admin endpoints) for on-demand runs + testing;
the scheduler only wires them to a cron trigger.
"""
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import SCHEDULER_ENABLED, SCHEDULER_ADP_HOUR, SCHEDULER_SENTIMENT_HOUR

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


# ── Jobs ──────────────────────────────────────────────────────────────────────

async def refresh_market_job() -> dict:
    """Append today's market snapshot for every tracked player (LLM-free):
    ESPN in-season **position rank** (derived from weekly projections, moves as
    projections update), frozen ADP, and live **% rostered**.

    One ESPN pull covers the whole pool; players are matched by normalized name. In-season
    ADP is static, so the rank line is what actually moves.
    """
    from datetime import datetime

    from database import AsyncSessionLocal
    from models.tracker import PlayerADPHistory
    from services import espn_service, tracker_service
    from services.projection_service import get_nfl_state
    from services.utils import normalize_name

    logger.info("[Scheduler] market refresh starting")
    state = await get_nfl_state()
    pool = await espn_service.get_espn_market_pool(state["season"], state["week"])
    if not pool:
        logger.warning("[Scheduler] ESPN market pool empty, skipping")
        return {"players": 0, "matched": 0, "missed": 0, "pool": 0}

    now = datetime.utcnow()
    matched, missed = 0, 0
    async with AsyncSessionLocal() as db:
        players = await tracker_service.get_trackable_players(db)
        for pid, name in players:
            entry = pool.get(normalize_name(name))
            if not entry:
                missed += 1
                continue
            db.add(PlayerADPHistory(
                player_id=pid,
                source="ESPN",
                adp=entry["adp"],
                position_rank=entry["position_rank"],
                overall_rank=entry["overall_rank"],
                percent_rostered=entry["percent_rostered"],
                recorded_at=now,
            ))
            matched += 1
        await db.commit()

    result = {"players": len(players), "matched": matched, "missed": missed, "pool": len(pool)}
    logger.info(f"[Scheduler] market refresh done, {result}")
    return result


async def sync_rosters_job() -> dict:
    """Re-sync every connected league (Sleeper and ESPN): roster rows plus this week's projections.
    Keeps Start/Sit current after waiver claims and saves a projection snapshot every
    week even if nobody opens the app (the recap depends on those)."""
    from sqlalchemy import select, update

    from database import AsyncSessionLocal
    from models.user import User, UserLeague
    from services.espn_service import EspnAuthError
    from services.league_service import sync_league
    from services.projection_service import get_nfl_state

    state = await get_nfl_state()
    if state.get("season_type") == "off":
        logger.info("[Scheduler] roster sync skipped, offseason")
        return {"leagues": 0, "synced": 0, "failed": 0, "skipped": "offseason"}

    async with AsyncSessionLocal() as db:
        pairs = (await db.execute(
            select(UserLeague.id, User.id)
            .join(User, User.id == UserLeague.user_id)
            # Only this season's leagues: last year's stay connected but are finished.
            .where(UserLeague.season == state["season"])
        )).all()

    synced, failed = 0, 0
    for ul_id, user_id in pairs:
        # One session per league so a bad league can't roll back the others.
        async with AsyncSessionLocal() as db:
            try:
                ul, user = await db.get(UserLeague, ul_id), await db.get(User, user_id)
                if await sync_league(db, user, ul, state) is None:
                    failed += 1
                    continue
                await db.commit()
                synced += 1
            except EspnAuthError:
                # Expired cookies: flag the user so the app shows the reconnect banner.
                await db.rollback()
                await db.execute(update(User).where(User.id == user_id).values(espn_needs_reconnect=True))
                await db.commit()
                failed += 1
                logger.warning(f"[Scheduler] ESPN cookies rejected for user={user_id}, flagged for reconnect")
            except Exception as e:
                await db.rollback()
                failed += 1
                logger.error(f"[Scheduler] roster sync failed for user_league={ul_id}: {e}")

    result = {"leagues": len(pairs), "synced": synced, "failed": failed}
    logger.info(f"[Scheduler] roster sync done, {result}")
    return result


# Each player's profile is a 4-pass Flash-Lite run. Require this much RPD headroom
# before starting a player so we don't half-run one (which would bank no graph point
# and leave the profile stale for the next run anyway).
PASSES_PER_PLAYER = 4

# Overlap guard: the cron and a manual admin trigger must never run this concurrently
# (they'd double-spend the budget and race on the same global profiles).
_sentiment_running = False


async def _representative_user_id() -> int:
    """A valid user_id to attribute global-profile writes to.

    Profiles are global (keyed by player_id); the user_id column only records who
    triggered the run. The scheduler has no request user, so use the lowest existing
    user id (defaulting to 1, the dev placeholder).
    """
    from sqlalchemy import text as _text

    from database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = (await db.execute(_text("SELECT id FROM users ORDER BY id LIMIT 1"))).first()
    return row[0] if row else 1


async def refresh_sentiment_job(force: bool = False) -> dict:
    """Re-analyze STALE tracked players, appending a sentiment-history point each time.

    Reuses the tracker's 4-pass pipeline. Cost controls:
      - stale-only (fresh profiles are reused, never re-run)
      - stops the moment the Flash-Lite budget can't cover a full player, leaving the
        rest for the next run (degraded profiles self-heal on retry)
      - paced ~16s/player to stay under Flash-Lite's ~15 RPM

    Awaited inline by the cron (max_instances=1); the admin trigger spawns it as a task
    since a full pass can take minutes.
    """
    import asyncio

    from database import AsyncSessionLocal
    from config import GEMINI_PRIMARY
    from services import llm_budget, tracker_service
    from services.tracker_service import ROSTER_PACE_SECONDS

    global _sentiment_running
    if _sentiment_running:
        logger.info("[Scheduler] sentiment refresh already running, skipping")
        return {"status": "already_running"}

    _sentiment_running = True
    analyzed = failed = 0
    budget_stopped = False
    try:
        async with AsyncSessionLocal() as db:
            stale, skipped_fresh = await tracker_service.get_stale_trackable_players(db, force=force)

        logger.info(f"[Scheduler] sentiment refresh starting, {len(stale)} stale, "
                    f"{skipped_fresh} fresh")
        rep_user_id = await _representative_user_id()
        loop = asyncio.get_event_loop()

        for pid, _name in stale:
            # Need headroom for a whole player (global cap AND Flash-Lite RPD).
            snap = llm_budget.usage()
            lite = snap["by_model"].get(GEMINI_PRIMARY, {})
            if snap["remaining"] < PASSES_PER_PLAYER or lite.get("remaining", 0) < PASSES_PER_PLAYER:
                budget_stopped = True
                logger.warning("[Scheduler] sentiment refresh halted, budget headroom "
                               f"below {PASSES_PER_PLAYER} passes; {analyzed} done, "
                               f"{len(stale) - analyzed} deferred to next run")
                break

            start = loop.time()
            try:
                ran = await tracker_service.analyze_one_player(rep_user_id, pid)
                if ran:
                    analyzed += 1
            except Exception as e:
                failed += 1
                logger.error(f"[Scheduler] sentiment refresh failed player={pid}: {e}")
            # Pace so 4 calls/player stays under ~15 RPM.
            await asyncio.sleep(max(0.0, ROSTER_PACE_SECONDS - (loop.time() - start)))
    finally:
        _sentiment_running = False

    result = {
        "stale": len(stale),
        "analyzed": analyzed,
        "skipped_fresh": skipped_fresh,
        "failed": failed,
        "budget_stopped": budget_stopped,
    }
    logger.info(f"[Scheduler] sentiment refresh done, {result}")
    return result


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """Start the scheduler if enabled. Idempotent; called from the FastAPI lifespan."""
    global _scheduler
    if not SCHEDULER_ENABLED:
        logger.info("[Scheduler] disabled (SCHEDULER_ENABLED=false), jobs run only on manual trigger")
        return
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    # 09:30 UTC lands just after Sleeper processes Wednesday waiver claims.
    _scheduler.add_job(sync_rosters_job, CronTrigger(hour="3,9,15,21", minute=30),
                       id="roster_sync", replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.add_job(refresh_market_job, CronTrigger(hour=SCHEDULER_ADP_HOUR, minute=0),
                       id="market_refresh", replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.add_job(refresh_sentiment_job, CronTrigger(hour=SCHEDULER_SENTIMENT_HOUR, minute=0),
                       id="sentiment_refresh", replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.start()
    logger.info(f"[Scheduler] started, rosters @ 03/09/15/21:30 UTC, ADP @ {SCHEDULER_ADP_HOUR:02d}:00 UTC, "
                f"sentiment @ {SCHEDULER_SENTIMENT_HOUR:02d}:00 UTC")


def shutdown_scheduler() -> None:
    """Stop the scheduler on app shutdown."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[Scheduler] shut down")
