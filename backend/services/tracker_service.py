"""
Player Tracker core logic.

- star_player:   Add to tracked_players, trigger 4-pass Gemini analysis.
- unstar_player: Set is_active=False.
- get_tracker:   Return all starred players with their stock profiles.
- refresh_profile: Re-run the 4-pass pipeline (called on major news).
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.news import PlayerNews, NewsAnalysis
from models.player import Player
from models.tracker import TrackedPlayer, PlayerStockProfile
from services import adp_service, historical_stats_service, nflreadpy_service, sentiment_service
from services.projection_service import get_nfl_state

logger = logging.getLogger(__name__)

# News types that trigger a profile re-analysis
MAJOR_NEWS_TYPES = {"INJURY", "CONTRACT", "TRANSACTION", "DEPTH_CHART"}


# ── Star / Unstar ─────────────────────────────────────────────────────────────

async def star_player(
    user_id: int,
    player_id: str,
    db: AsyncSession,
) -> dict:
    """
    Star a player for this user. If already starred (is_active=False), reactivates.
    Triggers the 4-pass Gemini analysis pipeline asynchronously.

    Returns {"status": "starred"|"already_starred", "player_id": str}
    """
    try:
        # Check if row exists (may be inactive from a previous unstar)
        existing = await db.get(TrackedPlayer, (user_id, player_id))

        if existing and existing.is_active:
            return {"status": "already_starred", "player_id": player_id}

        player = await db.get(Player, player_id)
        if not player:
            return {"status": "error", "detail": "Player not found"}

        if existing:
            existing.is_active = True
            existing.starred_at = datetime.utcnow()
        else:
            db.add(TrackedPlayer(
                user_id=user_id,
                player_id=player_id,
                player_name=player.name,
                position=player.position,
                nfl_team=player.nfl_team,
                is_active=True,
            ))

        await db.flush()

        # Trigger analysis (fire-and-forget — don't block the API response)
        asyncio.create_task(_run_analysis_for_player(user_id, player_id, player, db))

        return {"status": "starred", "player_id": player_id}

    except Exception as e:
        logger.error(f"[Tracker] star_player failed user={user_id} player={player_id}: {e}")
        return {"status": "error", "detail": str(e)}


async def unstar_player(user_id: int, player_id: str, db: AsyncSession) -> dict:
    """
    Soft-delete: set is_active=False. Stock profile is retained.
    Returns {"status": "unstarred"|"not_found"}
    """
    try:
        row = await db.get(TrackedPlayer, (user_id, player_id))
        if not row or not row.is_active:
            return {"status": "not_found"}
        row.is_active = False
        await db.flush()
        return {"status": "unstarred", "player_id": player_id}
    except Exception as e:
        logger.error(f"[Tracker] unstar_player failed user={user_id} player={player_id}: {e}")
        return {"status": "error", "detail": str(e)}


# ── Get tracker list ──────────────────────────────────────────────────────────

async def get_tracked_players(user_id: int, db: AsyncSession) -> list[dict]:
    """
    Return all active starred players for this user with their stock profiles.
    Sorted by combined_score DESC (most concerning first).
    """
    try:
        stmt = (
            select(TrackedPlayer)
            .where(TrackedPlayer.user_id == user_id, TrackedPlayer.is_active == True)
            .order_by(TrackedPlayer.starred_at.desc())
        )
        result = await db.execute(stmt)
        tracked = result.scalars().all()

        output = []
        for t in tracked:
            profile = await _get_stock_profile(t.player_id, db)
            adp_trend = await adp_service.compute_adp_trend(t.player_id, db)
            output.append(_build_tracker_card(t, profile, adp_trend))

        # Sort by combined_score descending (highest concern first)
        output.sort(key=lambda x: x.get("combined_score") or 0, reverse=True)
        return output

    except Exception as e:
        logger.error(f"[Tracker] get_tracked_players failed user={user_id}: {e}")
        return []


async def get_tracked_player_detail(
    user_id: int,
    player_id: str,
    db: AsyncSession,
) -> Optional[dict]:
    """Return full detail for a single tracked player."""
    try:
        row = await db.get(TrackedPlayer, (user_id, player_id))
        if not row or not row.is_active:
            return None

        profile = await _get_stock_profile(player_id, db)
        adp_trend = await adp_service.compute_adp_trend(player_id, db)
        stats = await historical_stats_service.sync_historical_stats(
            player_id, row.player_name, row.position or "", db
        )

        card = _build_tracker_card(row, profile, adp_trend)
        card["historical_stats"] = stats
        return card

    except Exception as e:
        logger.error(f"[Tracker] get_tracked_player_detail failed player={player_id}: {e}")
        return None


# ── Profile refresh ───────────────────────────────────────────────────────────

async def refresh_profile(
    user_id: int,
    player_id: str,
    db: AsyncSession,
    reason: str = "manual",
) -> bool:
    """
    Re-run the full 4-pass analysis for a player. Called on:
      - Manual refresh request
      - Major news trigger (INJURY / CONTRACT / TRANSACTION / DEPTH_CHART)

    Returns True on success.
    """
    try:
        player = await db.get(Player, player_id)
        if not player:
            return False

        tracked = await db.get(TrackedPlayer, (user_id, player_id))
        if not tracked or not tracked.is_active:
            return False

        logger.info(f"[Tracker] Refreshing profile player={player_id} reason={reason}")
        await _run_analysis_for_player(user_id, player_id, player, db)
        return True

    except Exception as e:
        logger.error(f"[Tracker] refresh_profile failed player={player_id}: {e}")
        return False


# ── Analysis pipeline ─────────────────────────────────────────────────────────

async def _run_analysis_for_player(
    user_id: int,
    player_id: str,
    player: Player,
    db: AsyncSession,  # kept for signature compatibility but NOT used — session is closed by the time this task runs
) -> None:
    """
    Assembles context and runs the 4-pass Gemini pipeline.
    Writes results to player_stock_profile (upsert).

    Opens its own DB session because this runs as a fire-and-forget background
    task; the request session passed by the caller is closed before this executes.
    """
    from database import AsyncSessionLocal

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

            # 8. Upsert player_stock_profile
            await _upsert_stock_profile(player_id, user_id, result, adp_trend, adp_delta, task_db)
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


# ── Card builder ──────────────────────────────────────────────────────────────

def _build_tracker_card(
    tracked: TrackedPlayer,
    profile: Optional[PlayerStockProfile],
    adp_trend: dict,
) -> dict:
    card = {
        "player_id": tracked.player_id,
        "player_name": tracked.player_name,
        "position": tracked.position,
        "nfl_team": tracked.nfl_team,
        "starred_at": tracked.starred_at.isoformat() if tracked.starred_at else None,
        "adp_trend": adp_trend,
        "profile_ready": profile is not None and profile.last_full_analysis is not None,
    }

    if profile:
        card.update({
            "overall_direction": profile.overall_direction,
            "overall_magnitude": profile.overall_magnitude,
            "concern_level": profile.concern_level,
            "concern_summary": profile.concern_summary,
            "worry_score": profile.worry_score,
            "combined_score": profile.combined_score,
            "bullish_factors": profile.bullish_factors,
            "bearish_factors": profile.bearish_factors,
            "sentiment_score": profile.sentiment_score,
            "sentiment_label": profile.sentiment_label,
            "dominant_themes": profile.dominant_themes,
            "contrarian_flag": profile.contrarian_flag,
            "sentiment_vs_stock": profile.sentiment_vs_stock,
            "historical_context": profile.historical_context,
            "short_term_outlook": profile.short_term_outlook,
            "long_term_outlook": profile.long_term_outlook,
            "draft_recommendation": profile.draft_recommendation,
            "last_full_analysis": (
                profile.last_full_analysis.isoformat() if profile.last_full_analysis else None
            ),
        })

    return card
