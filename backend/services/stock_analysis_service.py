"""
The 4-pass stock analysis for one player, and the rows it writes.

Split out of tracker_service, which had grown to 781 lines across eight concerns.
This is the leaf: everything else calls into it and it calls nothing back, so the
dependency runs one way (tracker_service -> here).

_run_analysis_for_player gathers the context (career stats, snaps, ADP, recent news,
current projection), runs sentiment_service's passes, upserts player_stock_profile,
and appends a dated point to player_sentiment_history for the over-time graph.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models.news import PlayerNews
from models.player import Player
from models.projection import Projection
from models.tracker import PlayerSentimentHistory, PlayerStockProfile, TrackedPlayer
from services import adp_service, historical_stats_service, nflreadpy_service, sentiment_service
from services.projection_service import get_nfl_state

logger = logging.getLogger(__name__)


async def _run_analysis_for_player(
    user_id: int,
    player_id: str,
    player: Player,
    db: AsyncSession,  # kept for signature compatibility but NOT used, session is closed by the time this task runs
) -> None:
    """
    Assembles context and runs the 4-pass Gemini pipeline.
    Writes results to player_stock_profile (upsert).

    Opens its own DB session because this runs as a fire-and-forget background
    task; the request session passed by the caller is closed before this executes.
    """
    try:
        async with AsyncSessionLocal() as task_db:
            # 1. Build stats context string for Gemini
            stats_context = await nflreadpy_service.build_stats_context(
                player.name, player.position or ""
            )

            # 2. Sync historical stats to DB
            await historical_stats_service.sync_historical_stats(
                player_id, player.name, player.position or "", task_db
            )

            # 3. Get ADP snapshot + trend
            adp_snapshot = await adp_service.fetch_and_store_adp(player_id, player.name, task_db)
            adp_trend_data = await adp_service.compute_adp_trend(player_id, task_db)
            adp_trend = adp_trend_data.get("trend", "STABLE")
            adp_delta = adp_trend_data.get("delta", 0.0)

            # 4. Assemble recent news context (last 10 items)
            recent_news = await _get_recent_news_context(player_id, task_db)

            # 5. Get current projection
            weighted_proj = await _get_current_projection(player_id, task_db)

            # 6. Get TrackedPlayer metadata
            tracked = await task_db.get(TrackedPlayer, (user_id, player_id))

            # 7. Run 4-pass analysis
            result = await sentiment_service.run_full_analysis(
                player_name=player.name,
                position=player.position or "N/A",
                nfl_team=player.nfl_team or "N/A",
                age=tracked.age if tracked else None,
                years_exp=tracked.years_exp if tracked else None,
                contract_year=tracked.contract_year if tracked else False,
                stats_context=stats_context,
                recent_news=recent_news,
                ffc_adp=adp_snapshot.get("ffc_adp"),
                fp_adp=adp_snapshot.get("fp_adp"),
                adp_trend=adp_trend,
                adp_delta=adp_delta,
                weighted_proj=weighted_proj,
            )

            if not result:
                logger.error(f"[Tracker] Sentiment analysis returned None for player={player_id}")
                return

            # 8. Upsert player_stock_profile (current values)
            await _upsert_stock_profile(player_id, user_id, result, adp_trend, adp_delta, task_db)
            # 9. Append a dated snapshot for the sentiment-over-time graph
            _append_sentiment_snapshot(player_id, result, task_db)
            await task_db.commit()
            logger.info(f"[Tracker] Profile written for player={player_id}")

    except Exception as e:
        logger.error(f"[Tracker] _run_analysis_for_player failed player={player_id}: {e}")


async def _get_recent_news_context(player_id: str, db: AsyncSession) -> str:
    """Fetch last 10 news items for this player and format as a context string."""
    try:
        stmt = (
            select(PlayerNews)
            .where(PlayerNews.player_id == player_id)
            .order_by(PlayerNews.published_at.desc().nullslast())
            .limit(10)
        )
        result = await db.execute(stmt)
        items = result.scalars().all()

        if not items:
            return "No recent news."

        lines = []
        for n in items:
            date_str = n.published_at.strftime("%Y-%m-%d") if n.published_at else "unknown date"
            lines.append(f"[{date_str}] {n.headline}")
            if n.news_body:
                lines.append(f"  {n.news_body[:300]}")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"[Tracker] Could not fetch news context for player={player_id}: {e}")
        return "No recent news."


async def _get_current_projection(player_id: str, db: AsyncSession) -> Optional[float]:
    """Get the most recent weighted projection for this player from the DB."""
    try:
        from models.projection import Projection
        from sqlalchemy import desc
        stmt = (
            select(Projection.weighted_proj)
            .where(Projection.player_id == player_id)
            .order_by(desc(Projection.season), desc(Projection.week))
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    except Exception:
        return None


def _append_sentiment_snapshot(player_id: str, result: dict, db: AsyncSession) -> None:
    """Append one dated sentiment point for the over-time graph.

    Skips degraded runs (null sentiment_score), a null point is useless on a chart,
    and the freshness-retry will re-run and bank a real point once scoring succeeds.
    Added to the session; committed by the caller alongside the profile upsert.
    """
    if result.get("sentiment_score") is None:
        return
    db.add(PlayerSentimentHistory(
        player_id=player_id,
        sentiment_score=result.get("sentiment_score"),
        sentiment_label=result.get("sentiment_label"),
        concern_level=result.get("concern_level"),
        worry_score=result.get("worry_score"),
        combined_score=result.get("combined_score"),
        overall_direction=result.get("overall_direction"),
    ))


async def _get_stock_profile(player_id: str, db: AsyncSession) -> Optional[PlayerStockProfile]:
    try:
        result = await db.execute(
            select(PlayerStockProfile).where(PlayerStockProfile.player_id == player_id)
        )
        return result.scalar_one_or_none()
    except Exception:
        return None


async def _upsert_stock_profile(
    player_id: str,
    user_id: int,
    result: dict,
    adp_trend: str,
    adp_delta: float,
    db: AsyncSession,
) -> None:
    existing = await _get_stock_profile(player_id, db)
    now = datetime.utcnow()

    if existing:
        existing.overall_direction = result.get("overall_direction")
        existing.overall_magnitude = result.get("overall_magnitude")
        existing.concern_level = result.get("concern_level")
        existing.concern_summary = result.get("concern_summary")
        existing.worry_score = result.get("worry_score")
        existing.combined_score = result.get("combined_score")
        existing.bullish_factors = result.get("bullish_factors")
        existing.bearish_factors = result.get("bearish_factors")
        existing.adp_trend = adp_trend
        existing.adp_trend_delta = adp_delta
        existing.sentiment_score = result.get("sentiment_score")
        existing.sentiment_label = result.get("sentiment_label")
        existing.dominant_themes = result.get("dominant_themes")
        existing.sentiment_vs_stock = result.get("sentiment_vs_stock")
        existing.alignment_note = result.get("alignment_note")
        existing.contrarian_flag = result.get("contrarian_flag", False)
        existing.historical_context = result.get("historical_context")
        existing.short_term_outlook = result.get("short_term_outlook")
        existing.long_term_outlook = result.get("long_term_outlook")
        existing.draft_recommendation = result.get("draft_recommendation")
        existing.last_full_analysis = now
    else:
        db.add(PlayerStockProfile(
            player_id=player_id,
            user_id=user_id,
            overall_direction=result.get("overall_direction"),
            overall_magnitude=result.get("overall_magnitude"),
            concern_level=result.get("concern_level"),
            concern_summary=result.get("concern_summary"),
            worry_score=result.get("worry_score"),
            combined_score=result.get("combined_score"),
            bullish_factors=result.get("bullish_factors"),
            bearish_factors=result.get("bearish_factors"),
            adp_trend=adp_trend,
            adp_trend_delta=adp_delta,
            sentiment_score=result.get("sentiment_score"),
            sentiment_label=result.get("sentiment_label"),
            dominant_themes=result.get("dominant_themes"),
            sentiment_vs_stock=result.get("sentiment_vs_stock"),
            alignment_note=result.get("alignment_note"),
            contrarian_flag=result.get("contrarian_flag", False),
            historical_context=result.get("historical_context"),
            short_term_outlook=result.get("short_term_outlook"),
            long_term_outlook=result.get("long_term_outlook"),
            draft_recommendation=result.get("draft_recommendation"),
            last_full_analysis=now,
        ))
