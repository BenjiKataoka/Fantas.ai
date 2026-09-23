"""
News scraper orchestrator, Phase 4.5.

Responsibilities:
1. Determine which players are starred (any user) vs rostered-only vs untracked.
2. Enforce per-player refresh windows via last_checked timestamp on player_news.
3. Fetch news from RotoWire + ESPN and deduplicate by source_url.
4. Route each item through the rule filter.
5. For rostered-only: write rule filter result directly, no Gemini.
6. For starred: enqueue eligible items in the Gemini queue.
7. Drain the queue (up to the rate limit) and run news_analysis_service.

Refresh windows (from season_type):
  - starred, team playing today:     1h  (regular/post); 4h pre; 24h off
  - starred, team NOT playing today: 2h  (regular/post); 4h pre; 24h off
  - rostered-only:                   4h  (regular/post/pre); never (off)

Gemini gate:
  - "Playing today" only affects refresh TTL, not whether Gemini fires.
  - INJURY and TRANSACTION news always bypass the game-day gate for starred players
    (a player ruled out on Friday still needs immediate analysis).
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.player import Player
from models.news import PlayerNews, NewsAnalysis
from models.roster import MyRoster
from models.tracker import TrackedPlayer
from services import rotowire_service, nfl_service, rss_service
from services.nfl_service import get_teams_playing_today
from services.rule_filter_service import apply_rule_filter, should_run_gemini, classify_news_type, FilterResult
from services.news_analysis_service import analyze_news_item
from services.news_queue_service import get_queue, QueuedItem
from services.utils import normalize_name

logger = logging.getLogger(__name__)


# ── Refresh window helpers ─────────────────────────────────────────────────────

def _starred_ttl_minutes(season_type: str, team_playing_today: bool = False) -> int:
    if season_type == "off":
        return 24 * 60
    if season_type == "pre":
        return 4 * 60
    # regular / post: 1h if this player's team is playing today, 2h otherwise
    return 60 if team_playing_today else 120


def _rostered_ttl_minutes(season_type: str) -> Optional[int]:
    """Returns None when rostered-only players should never be refreshed."""
    if season_type == "off":
        return None
    return 4 * 60


def _is_due(last_checked: Optional[datetime], ttl_minutes: Optional[int]) -> bool:
    """Returns True if a refresh is due. ttl_minutes=None means never refresh."""
    if ttl_minutes is None:
        return False
    if last_checked is None:
        return True
    return datetime.utcnow() >= last_checked + timedelta(minutes=ttl_minutes)


# ── Player tier resolution ─────────────────────────────────────────────────────

async def _get_player_tiers(db: AsyncSession) -> tuple[set[str], set[str]]:
    """
    Returns (starred_ids, rostered_ids).
    starred_ids: player_ids starred by ANY user across the app.
    rostered_ids: player_ids on any user's roster but NOT starred by anyone.
    """
    # Players starred by any user
    starred_result = await db.execute(
        select(TrackedPlayer.player_id).where(TrackedPlayer.is_active == True)
    )
    starred_ids = {row[0] for row in starred_result.fetchall()}

    # Players rostered by any user
    rostered_result = await db.execute(select(MyRoster.player_id))
    rostered_ids = {row[0] for row in rostered_result.fetchall()} - starred_ids

    return starred_ids, rostered_ids


# ── Last-checked lookup ────────────────────────────────────────────────────────

async def _get_last_checked(player_id: str, db: AsyncSession) -> Optional[datetime]:
    """Returns the most recent created_at for any news item for this player."""
    result = await db.execute(
        select(func.max(PlayerNews.created_at)).where(PlayerNews.player_id == player_id)
    )
    return result.scalar_one_or_none()


# ── Player context builder ─────────────────────────────────────────────────────

async def _build_player_context(player_id: str, db: AsyncSession) -> dict:
    """Fetch player row from DB and build the context dict for Gemini."""
    player = await db.get(Player, player_id)
    if not player:
        return {"player_name": "Unknown", "position": "N/A", "nfl_team": "N/A",
                "weighted_proj": None, "trending_status": None, "stats_context": None}

    # Latest weighted projection for this player
    from models.projection import Projection
    proj_result = await db.execute(
        select(Projection)
        .where(Projection.player_id == player_id)
        .order_by(Projection.week.desc())
        .limit(1)
    )
    proj = proj_result.scalar_one_or_none()

    return {
        "player_name": player.name,
        "position": player.position or "N/A",
        "nfl_team": player.nfl_team or "N/A",
        "weighted_proj": proj.weighted_proj if proj else None,
        "trending_status": None,   # Phase 4.6: Sleeper trending enrichment
        "stats_context": None,     # Phase 4.6: nflreadpy snap/target stats
    }


# ── News item resolution, match raw news to a player_id ──────────────────────

async def _resolve_player_id(
    player_name: str,
    espn_athlete_id: Optional[str],
    db: AsyncSession,
    player_cache: dict,  # mutable dict for in-memory caching across items
) -> Optional[str]:
    """
    Match a news item to a player_id.
    Tries espn_athlete_id first, then normalized name lookup.
    """
    if espn_athlete_id:
        cache_key = f"espn_{espn_athlete_id}"
        if cache_key not in player_cache:
            result = await db.execute(
                select(Player.player_id).where(Player.espn_athlete_id == espn_athlete_id)
            )
            row = result.scalar_one_or_none()
            player_cache[cache_key] = row
        if player_cache[cache_key]:
            return player_cache[cache_key]

    # Normalized name fallback
    normalized = normalize_name(player_name)
    cache_key = f"name_{normalized}"
    if cache_key not in player_cache:
        result = await db.execute(
            select(Player.player_id, Player.name).where(
                func.lower(Player.name).contains(normalized[:10])
            ).limit(10)
        )
        rows = result.fetchall()
        match = None
        for pid, name in rows:
            if normalize_name(name) == normalized:
                match = pid
                break
        player_cache[cache_key] = match
    return player_cache[cache_key]


# ── Core orchestration ─────────────────────────────────────────────────────────

async def scrape_and_analyze(
    db: AsyncSession,
    season_type: str,
    force_refresh: bool = False,
) -> dict:
    """
    Main entry point called from the /api/news router.

    1. Fetch today's schedule + news from RotoWire + ESPN concurrently.
    2. Deduplicate by source_url.
    3. Match to player tiers.
    4. Apply rule filter.
    5. Persist new PlayerNews rows.
    6. Enqueue starred players for Gemini.
    7. Drain queue up to rate limit.

    Returns summary dict with counts.
    """
    starred_ids, rostered_ids = await _get_player_tiers(db)
    all_tracked_ids = starred_ids | rostered_ids

    # Names for the RSS matcher: general feeds aren't player-keyed, so RSS matches
    # entries against this tracked-name set and drops everything else.
    tracked_names: list[str] = []
    if all_tracked_ids:
        name_rows = await db.execute(
            select(Player.name).where(Player.player_id.in_(all_tracked_ids))
        )
        tracked_names = [row[0] for row in name_rows.fetchall()]

    # Hand the connection back before the slow network fetch. Holding it idle through the
    # RotoWire retries let Neon close it, and the next query failed mid-operation.
    await db.commit()

    # Fetch today's schedule + raw news concurrently
    rw_news, espn_news, rss_news, teams_playing_today = await asyncio.gather(
        asyncio.to_thread(
            rotowire_service.scrape_rotowire_news,
            force_refresh=force_refresh,
        ),
        nfl_service.get_espn_news(force_refresh=force_refresh),
        rss_service.fetch_rss_news(tracked_names, force_refresh=force_refresh),
        get_teams_playing_today(force_refresh=force_refresh),
    )
    all_raw = rw_news + espn_news + rss_news

    # Existing source_urls to deduplicate
    existing_urls_result = await db.execute(
        select(PlayerNews.source_url).where(PlayerNews.source_url.isnot(None))
    )
    existing_urls: set[str] = {row[0] for row in existing_urls_result.fetchall()}

    player_cache: dict = {}
    new_items_count = 0
    skipped_untracked = 0
    skipped_dedup = 0
    enqueued_for_gemini = 0
    rule_filtered = 0

    queue = get_queue()

    for raw in all_raw:
        source_url = raw.get("source_url")

        # Deduplication
        if source_url and source_url in existing_urls:
            skipped_dedup += 1
            continue

        player_name = raw.get("player_name", "")
        espn_athlete_id = raw.get("espn_athlete_id")

        player_id = await _resolve_player_id(player_name, espn_athlete_id, db, player_cache)
        if not player_id or player_id not in all_tracked_ids:
            skipped_untracked += 1
            continue

        is_starred = player_id in starred_ids
        is_rostered = player_id in rostered_ids

        # Check refresh window, TTL is per-player based on whether their team plays today
        if not force_refresh:
            last_checked = await _get_last_checked(player_id, db)
            if is_starred:
                # Look up this player's team from the DB to check the schedule
                player_row = await db.get(Player, player_id)
                team_abbrev = (player_row.nfl_team or "").upper() if player_row else ""
                team_playing_today = team_abbrev in teams_playing_today
                ttl = _starred_ttl_minutes(season_type, team_playing_today)
            else:
                ttl = _rostered_ttl_minutes(season_type)
            if not _is_due(last_checked, ttl):
                continue

        # Apply rule filter
        headline = raw.get("headline", "")
        news_body = raw.get("news_body")
        filter_result: FilterResult = apply_rule_filter(headline, news_body, season_type)

        # Persist news item
        news_item = PlayerNews(
            player_id=player_id,
            source=raw.get("source", "UNKNOWN"),
            headline=headline,
            news_body=news_body,
            published_at=raw.get("published_at"),
            source_url=source_url,
            # Prefer the scoring rule's type hint; else classify from category keywords
            # so items like "might miss Week 2 due to injury" still label as INJURY.
            news_type=filter_result.news_type_hint or classify_news_type(headline, news_body),
            is_rostered=True,
            analysis_status="PENDING",
        )
        db.add(news_item)
        await db.flush()  # get news_item.id

        if source_url:
            existing_urls.add(source_url)

        new_items_count += 1

        # Rostered-only: write rule result directly, no Gemini
        if is_rostered:
            if filter_result.matched:
                analysis = NewsAnalysis(
                    news_id=news_item.id,
                    player_id=player_id,
                    stock_direction=filter_result.direction,
                    stock_magnitude=filter_result.magnitude,
                    confidence_score=filter_result.confidence,
                    analysis_model="rule_filter",
                )
                db.add(analysis)
                news_item.analysis_status = "COMPLETE"
            else:
                news_item.analysis_status = "SKIPPED"
            rule_filtered += 1
            continue

        # Injury/transaction-adjacent news bypasses the offseason gate for starred players,
        # a player ruled out on Friday still needs immediate Gemini analysis even in offseason.
        # offseason_significant is set by the rule filter for any injury/trade/signing keyword,
        # regardless of whether a specific rule matched.
        effective_season_type = (
            "regular" if filter_result.offseason_significant and season_type == "off"
            else season_type
        )

        # Starred: check if we should run Gemini
        if not should_run_gemini(filter_result, is_starred=True, season_type=effective_season_type):
            # Rule matched, write result directly
            if filter_result.matched:
                analysis = NewsAnalysis(
                    news_id=news_item.id,
                    player_id=player_id,
                    stock_direction=filter_result.direction,
                    stock_magnitude=filter_result.magnitude,
                    confidence_score=filter_result.confidence,
                    analysis_model="rule_filter",
                )
                db.add(analysis)
                news_item.analysis_status = "COMPLETE"
            else:
                news_item.analysis_status = "SKIPPED"
            rule_filtered += 1
            continue

        # Enqueue for Gemini
        added = queue.enqueue(QueuedItem(
            news_id=news_item.id,
            player_id=player_id,
            player_name=player_name,
            is_starred=True,
        ))
        if added:
            enqueued_for_gemini += 1

    # Save the new items now, and again after each Gemini call below, so no connection sits
    # open across a model round trip either.
    await db.commit()

    # Drain the queue up to the rate limit
    gemini_ran = 0
    while queue.can_call() and queue.pending_count() > 0:
        item = queue.dequeue()
        if item is None:
            break

        # Load the news item we just persisted
        news_item_result = await db.execute(
            select(PlayerNews).where(PlayerNews.id == item.news_id)
        )
        news_item = news_item_result.scalar_one_or_none()
        if not news_item:
            continue

        player_context = await _build_player_context(item.player_id, db)
        queue.record_call()

        analysis = await analyze_news_item(news_item, player_context, db)
        if analysis:
            db.add(analysis)
            news_item.analysis_status = "COMPLETE"
        else:
            news_item.analysis_status = "SKIPPED"
        gemini_ran += 1
        await db.commit()

    await db.commit()

    return {
        "new_items": new_items_count,
        "skipped_dedup": skipped_dedup,
        "skipped_untracked": skipped_untracked,
        "rule_filtered": rule_filtered,
        "gemini_ran": gemini_ran,
        "gemini_queue_remaining": queue.pending_count(),
        "queue_status": queue.status(),
    }
