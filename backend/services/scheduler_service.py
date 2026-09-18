"""
Autonomous background scheduler (APScheduler, in-process).

Two daily UTC jobs:
  - ADP refresh   (LLM-free): append today's ADP/rank for every tracked player.
  - Sentiment refresh (LLM):  re-analyze stale tracked players, appending sentiment
                              history — budget/RPD-gated + paced. (built in the next pass)

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
    ESPN in-season **position rank** (derived from weekly projections — moves as
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
        logger.warning("[Scheduler] ESPN market pool empty — skipping")
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
    logger.info(f"[Scheduler] market refresh done — {result}")
    return result


async def refresh_sentiment_job() -> dict:
    """Re-analyze stale tracked players, appending sentiment history. Built next pass."""
    logger.info("[Scheduler] sentiment refresh not yet implemented — skipping")
    return {"status": "not_implemented"}


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """Start the scheduler if enabled. Idempotent; called from the FastAPI lifespan."""
    global _scheduler
    if not SCHEDULER_ENABLED:
        logger.info("[Scheduler] disabled (SCHEDULER_ENABLED=false) — jobs run only on manual trigger")
        return
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(refresh_market_job, CronTrigger(hour=SCHEDULER_ADP_HOUR, minute=0),
                       id="market_refresh", replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.add_job(refresh_sentiment_job, CronTrigger(hour=SCHEDULER_SENTIMENT_HOUR, minute=0),
                       id="sentiment_refresh", replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.start()
    logger.info(f"[Scheduler] started — ADP @ {SCHEDULER_ADP_HOUR:02d}:00 UTC, "
                f"sentiment @ {SCHEDULER_SENTIMENT_HOUR:02d}:00 UTC")


def shutdown_scheduler() -> None:
    """Stop the scheduler on app shutdown."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[Scheduler] shut down")
