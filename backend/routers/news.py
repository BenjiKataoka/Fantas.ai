"""
GET /api/news

Returns news feed filtered to the requesting user's players.

Response shapes:
  - Starred player with full Gemini analysis → full_analysis card
  - Starred player with rule-filter-only result → signal_only card
  - Rostered-only player → signal_only card (BULL/BEAR/NEUTRAL badge)
  - Untracked → never returned

Query params:
  - force_refresh (bool, default=False)
"""

import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.news import PlayerNews, NewsAnalysis
from models.roster import MyRoster
from models.tracker import TrackedPlayer
from models.user import User
from auth import get_current_user
from services.projection_service import get_nfl_state
from services.news_scraper_service import scrape_and_analyze

router = APIRouter()
logger = logging.getLogger(__name__)

# Days of news history to return per call
NEWS_LOOKBACK_DAYS = 7


@router.get("/news")
async def get_news(
    force_refresh: bool = Query(default=False, description="Bypass cache and re-scrape"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the news feed for this user's roster + starred players.
    Triggers a scrape if any player's last_checked is stale.
    """
    nfl_state = await get_nfl_state()
    season_type = nfl_state.get("season_type", "off")

    # Run scraper / queue drainer — game-day check is now per-player inside the scraper
    scrape_summary = await scrape_and_analyze(
        db=db,
        season_type=season_type,
        force_refresh=force_refresh,
    )

    # Fetch this user's starred player_ids
    starred_result = await db.execute(
        select(TrackedPlayer.player_id).where(
            TrackedPlayer.user_id == user.id,
            TrackedPlayer.is_active == True,
        )
    )
    user_starred_ids = {row[0] for row in starred_result.fetchall()}

    # Fetch this user's rostered player_ids
    rostered_result = await db.execute(
        select(MyRoster.player_id).where(MyRoster.user_id == user.id)
    )
    user_rostered_ids = {row[0] for row in rostered_result.fetchall()} - user_starred_ids

    all_user_player_ids = user_starred_ids | user_rostered_ids
    if not all_user_player_ids:
        return {
            "news": [],
            "total": 0,
            "season_type": season_type,
            "scrape_summary": scrape_summary,
            "warning": "No players on roster or watchlist.",
        }

    # Fetch recent news for this user's players, with analysis joined
    from datetime import timedelta, datetime
    lookback = datetime.utcnow() - timedelta(days=NEWS_LOOKBACK_DAYS)

    news_result = await db.execute(
        select(PlayerNews)
        .options(selectinload(PlayerNews.analysis))
        .where(
            PlayerNews.player_id.in_(all_user_player_ids),
            PlayerNews.created_at >= lookback,
        )
        .order_by(PlayerNews.created_at.desc())
        .limit(100)
    )
    news_items = news_result.scalars().all()

    # Build response cards
    feed = []
    for item in news_items:
        is_starred = item.player_id in user_starred_ids
        card = _build_card(item, is_starred=is_starred)
        feed.append(card)

    return {
        "news": feed,
        "total": len(feed),
        "season_type": season_type,
        "week": nfl_state.get("week"),
        "scrape_summary": scrape_summary,
    }


def _build_card(item: PlayerNews, is_starred: bool) -> dict:
    """
    Build a response card for a single news item.

    Full analysis card: starred player + Gemini ran (analysis_tier="full")
    Signal-only card:  rule filter result or rostered-only (analysis_tier="signal_only")
    """
    analysis: NewsAnalysis | None = item.analysis

    base = {
        "news_id": item.id,
        "player_id": item.player_id,
        "source": item.source,
        "headline": item.headline,
        "news_body": item.news_body,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "news_type": item.news_type,
        "analysis_status": item.analysis_status,
    }

    if not analysis:
        base["analysis_tier"] = "pending"
        return base

    # Signal-only: rule-filter result or rostered-only player
    if not is_starred or analysis.analysis_model == "rule_filter":
        base["analysis_tier"] = "signal_only"
        base["stock_direction"] = analysis.stock_direction
        base["stock_magnitude"] = analysis.stock_magnitude
        base["confidence_score"] = analysis.confidence_score
        return base

    # Full analysis card (Gemini ran)
    base["analysis_tier"] = "full"
    base["summary"] = analysis.summary
    base["stock_direction"] = analysis.stock_direction
    base["stock_magnitude"] = analysis.stock_magnitude
    base["confidence_score"] = analysis.confidence_score
    base["short_term_impact"] = analysis.short_term_impact
    base["long_term_impact"] = analysis.long_term_impact
    base["context_notes"] = analysis.context_notes
    base["contradictions_flagged"] = analysis.contradictions_flagged
    base["contradiction_detail"] = analysis.contradiction_detail
    base["analysis_model"] = analysis.analysis_model
    return base
