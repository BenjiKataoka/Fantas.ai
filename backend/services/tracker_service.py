"""
Player Tracker core logic.

- star_player:   Add to tracked_players, trigger 4-pass Gemini analysis.
- unstar_player: Set is_active=False.
- get_tracker:   Return all starred players with their stock profiles.
- refresh_profile: Re-run the 4-pass pipeline (called on major news).
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.news import PlayerNews, NewsAnalysis
from models.player import Player
from models.roster import MyRoster
from models.tracker import TrackedPlayer, PlayerStockProfile, PlayerSentimentHistory
from services import adp_service, historical_stats_service, nflreadpy_service, sentiment_service, sleeper_service
from services.projection_service import get_nfl_state

logger = logging.getLogger(__name__)

# News types that trigger a profile re-analysis
MAJOR_NEWS_TYPES = {"INJURY", "CONTRACT", "TRANSACTION", "DEPTH_CHART"}

# Seconds to wait between players in a batch roster analysis. Each player is 4 Flash-Lite
# calls; Flash-Lite's free tier allows ~15 requests/minute, so ~16s/player (4 calls per
# ~16s ≈ 15 RPM) keeps a full roster run safely under the rate limit. Network latency for
# the 4 sequential passes usually covers most of this, so the added sleep is small.
ROSTER_PACE_SECONDS = 16.0


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
            # Free agents from the waiver wire usually aren't in our pool yet.
            sp = (await sleeper_service.get_all_players()).get(player_id)
            if not sp or not sp.get("full_name"):
                return {"status": "error", "detail": "Player not found"}
            espn_id = str(sp["espn_id"]) if sp.get("espn_id") is not None else None
            player = Player(player_id=player_id, name=sp["full_name"], position=sp.get("position"),
                            nfl_team=sp.get("team"), sleeper_id=player_id, espn_id=espn_id,
                            espn_athlete_id=espn_id, injury_status=sp.get("injury_status") or "Active")
            db.add(player)
            await db.flush()

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

        # Trigger analysis (fire-and-forget, don't block the API response)
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


# ── Batch roster analysis ─────────────────────────────────────────────────────

# User IDs with a roster deep-dive currently in flight. Prevents a second click (or a
# second browser tab) from spawning a duplicate worker and doubling Gemini spend.
# In-memory only, cleared on process restart, which is fine for a soft guard.
_roster_runs: set[int] = set()


async def _season_ttl_hours(db: AsyncSession) -> float:
    """Freshness window for a stock profile, by season state.

    Offseason moves slowly (24h); in-season/preseason news turns over fast (6h).
    """
    try:
        state = await get_nfl_state()
        return 24.0 if state.get("season_type") == "off" else 6.0
    except Exception:
        return 24.0  # conservative default, avoids needless re-analysis on a state miss


async def _profile_is_fresh(player_id: str, db: AsyncSession, ttl_hours: float) -> bool:
    """True if a COMPLETE stock profile exists and is younger than the TTL."""
    profile = await db.get(PlayerStockProfile, player_id)
    if not profile or not profile.last_full_analysis:
        return False
    # A profile missing its concern/sentiment scores is incomplete (a transient Pass 3/4
    # failure nulled them). Treat it as stale so the next run retries and repairs it.
    if profile.concern_level is None or profile.sentiment_score is None:
        return False
    age = datetime.utcnow() - profile.last_full_analysis
    return age.total_seconds() < ttl_hours * 3600


async def analyze_roster(user_id: int, db: AsyncSession, force: bool = False) -> dict:
    """
    Deep-dive every player on this user's roster, skipping any with a fresh profile.

    Profiles are global (keyed by player_id), so this reuses analysis another user
    already paid for. Runs as a single paced background worker to respect the
    Flash-Lite rate limit, returns immediately with the queued/skipped counts.
    """
    player_ids = (
        await db.execute(select(MyRoster.player_id).where(MyRoster.user_id == user_id).distinct())
    ).scalars().all()

    if not player_ids:
        return {"status": "empty", "queued": 0, "skipped_fresh": 0, "total": 0}

    # Don't spawn a duplicate worker if one is already draining this user's roster.
    if user_id in _roster_runs:
        return {"status": "already_running", "queued": 0,
                "skipped_fresh": 0, "total": len(player_ids)}

    ttl = await _season_ttl_hours(db)
    to_analyze: list[str] = []
    for pid in player_ids:
        if force or not await _profile_is_fresh(pid, db, ttl):
            to_analyze.append(pid)

    if to_analyze:
        # Mark in-flight before spawning so a rapid second call is rejected above.
        _roster_runs.add(user_id)
        # One background worker drains the list at a paced rate (see ROSTER_PACE_SECONDS).
        asyncio.create_task(_analyze_roster_worker(user_id, to_analyze))

    return {
        "status": "started" if to_analyze else "all_fresh",
        "queued": len(to_analyze),
        "skipped_fresh": len(player_ids) - len(to_analyze),
        "total": len(player_ids),
    }


async def get_trackable_players(db: AsyncSession) -> list[tuple[str, str]]:
    """Distinct (player_id, name) for every player anyone rosters or has starred.

    The scheduler refreshes exactly this set, never all of NFL, and it's deduped
    because ADP/profiles are global (keyed by player_id).
    """
    stmt = text(
        "SELECT p.player_id, p.name FROM players p "
        "WHERE p.player_id IN ("
        "  SELECT player_id FROM my_roster "
        "  UNION "
        "  SELECT player_id FROM tracked_players WHERE is_active = TRUE"
        ")"
    )
    rows = (await db.execute(stmt)).mappings().all()
    return [(r["player_id"], r["name"]) for r in rows]


async def get_stale_trackable_players(
    db: AsyncSession, force: bool = False
) -> tuple[list[tuple[str, str]], int]:
    """Split the global trackable set into (stale, count_of_fresh_skipped).

    "Stale" = no complete profile, or one older than the season-aware TTL. This is the
    scheduler's work list, fresh profiles are reused, never re-analyzed.
    """
    players = await get_trackable_players(db)
    ttl = await _season_ttl_hours(db)
    stale: list[tuple[str, str]] = []
    for pid, name in players:
        if force or not await _profile_is_fresh(pid, db, ttl):
            stale.append((pid, name))
    return stale, len(players) - len(stale)


async def analyze_one_player(user_id: int, player_id: str) -> bool:
    """Load a player and run the full 4-pass profile. Returns True if it ran.

    Public entry point for callers outside a request (the scheduler) that have only a
    player_id. Opens its own sessions, same as the fire-and-forget analysis path.
    """
    from database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        player = await s.get(Player, player_id)
    if player is None:
        return False
    await _run_analysis_for_player(user_id, player_id, player, None)
    return True


async def roster_analysis_status(user_id: int, db: AsyncSession) -> dict:
    """How many of the user's rostered players have a completed stock profile.

    Lets the frontend poll a batch run to completion and fill gauges in as they land.
    """
    player_ids = (
        await db.execute(select(MyRoster.player_id).where(MyRoster.user_id == user_id).distinct())
    ).scalars().all()
    if not player_ids:
        return {"total": 0, "ready": 0, "pending": 0}

    rows = (
        await db.execute(
            select(PlayerStockProfile.player_id).where(
                PlayerStockProfile.player_id.in_(player_ids),
                PlayerStockProfile.last_full_analysis.isnot(None),
            )
        )
    ).scalars().all()
    ready = len(set(rows))
    return {
        "total": len(player_ids),
        "ready": ready,
        "pending": len(player_ids) - ready,
        "running": user_id in _roster_runs,
    }


async def _analyze_roster_worker(user_id: int, player_ids: list[str]) -> None:
    """Sequentially deep-dive each player, paced to stay under the Flash-Lite RPM limit."""
    from database import AsyncSessionLocal

    logger.info(f"[Tracker] Roster analysis started user={user_id} players={len(player_ids)}")
    loop = asyncio.get_event_loop()
    try:
        for pid in player_ids:
            start = loop.time()
            try:
                async with AsyncSessionLocal() as s:
                    player = await s.get(Player, pid)
                if player is None:
                    continue
                # player is detached here but only its already-loaded scalar attrs are read.
                await _run_analysis_for_player(user_id, pid, player, None)
            except Exception as e:
                logger.error(f"[Tracker] roster worker failed player={pid}: {e}")
            # Pace the next player so 4 calls/player stays within ~15 RPM.
            elapsed = loop.time() - start
            await asyncio.sleep(max(0.0, ROSTER_PACE_SECONDS - elapsed))
    finally:
        # Always clear the in-flight flag, even if the worker errors out.
        _roster_runs.discard(user_id)
        logger.info(f"[Tracker] Roster analysis finished user={user_id}")


# ── Analysis pipeline ─────────────────────────────────────────────────────────

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


# ── Stock profile serialization ───────────────────────────────────────────────

def serialize_stock_profile(profile: Optional[PlayerStockProfile]) -> Optional[dict]:
    """Flatten a completed PlayerStockProfile to the JSON shape the frontend renders.

    Returns None when there's no finished analysis, so callers can show an
    "not analyzed yet" state. Omits the 200-word historical_context to keep roster
    payloads light, the tracker detail view fetches that separately.
    """
    if not profile or not profile.last_full_analysis:
        return None
    return {
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
        "short_term_outlook": profile.short_term_outlook,
        "long_term_outlook": profile.long_term_outlook,
        "draft_recommendation": profile.draft_recommendation,
        "last_full_analysis": profile.last_full_analysis.isoformat(),
    }


async def get_stock_profiles_for(player_ids: list[str], db: AsyncSession) -> dict[str, dict]:
    """Batch-fetch current stock profiles for a set of players → {player_id: serialized}.

    Only completed profiles are returned; missing/unanalyzed players are absent from
    the map. Profiles are global, so this reuses whatever any user has already analyzed.
    """
    if not player_ids:
        return {}
    rows = (
        await db.execute(
            select(PlayerStockProfile).where(
                PlayerStockProfile.player_id.in_(player_ids),
                PlayerStockProfile.last_full_analysis.isnot(None),
            )
        )
    ).scalars().all()
    return {r.player_id: serialize_stock_profile(r) for r in rows}


# ── Metric-over-time (graph) ──────────────────────────────────────────────────

# range → (window length, SQL date_trunc bucket or None for raw points)
_RANGE_CONFIG = {
    "1w":     (timedelta(days=7),   None),    # raw points, recent detail
    "1m":     (timedelta(days=31),  "day"),   # daily average
    "season": (timedelta(days=240), "week"),  # weekly average, whole trail
}


async def get_sentiment_history(player_id: str, rng: str, db: AsyncSession) -> dict:
    """Chart-ready metric series for one player, downsampled by range.

    Returns the real per-date metrics, sentiment, concern, overall ADP, and position
    rank, each on its own scale; the frontend focuses one metric at a time on a real,
    player-scaled axis. Aggregated server-side (date_trunc + AVG): 1w = raw, 1m = daily
    average, season = weekly average. ADP/rank are joined from player_adp_history.
    """
    rng = rng if rng in _RANGE_CONFIG else "season"
    window, bucket = _RANGE_CONFIG[rng]
    since = datetime.utcnow() - window
    sp = {"pid": player_id, "since": since}
    ap = {"pid": player_id, "since": since}

    if bucket is None:
        s_stmt = text(
            "SELECT recorded_at AS t, sentiment_score AS s, concern_level AS c "
            "FROM player_sentiment_history "
            "WHERE player_id=:pid AND recorded_at>=:since AND sentiment_score IS NOT NULL "
            "ORDER BY recorded_at"
        )
        a_stmt = text(
            "SELECT recorded_at AS t, adp AS a, position_rank AS r, percent_rostered AS pr "
            "FROM player_adp_history "
            "WHERE player_id=:pid AND recorded_at>=:since "
            "AND (adp IS NOT NULL OR position_rank IS NOT NULL OR percent_rostered IS NOT NULL) "
            "ORDER BY recorded_at"
        )
    else:
        sp["b"] = ap["b"] = bucket
        s_stmt = text(
            "SELECT date_trunc(:b, recorded_at) AS t, AVG(sentiment_score) AS s, AVG(concern_level) AS c "
            "FROM player_sentiment_history "
            "WHERE player_id=:pid AND recorded_at>=:since AND sentiment_score IS NOT NULL "
            "GROUP BY 1 ORDER BY 1"
        )
        a_stmt = text(
            "SELECT date_trunc(:b, recorded_at) AS t, AVG(adp) AS a, AVG(position_rank) AS r, "
            "AVG(percent_rostered) AS pr FROM player_adp_history "
            "WHERE player_id=:pid AND recorded_at>=:since "
            "AND (adp IS NOT NULL OR position_rank IS NOT NULL OR percent_rostered IS NOT NULL) "
            "GROUP BY 1 ORDER BY 1"
        )

    s_rows = (await db.execute(s_stmt, sp)).mappings().all()
    a_rows = (await db.execute(a_stmt, ap)).mappings().all()

    # Merge on the UNION of dates from both tables, market metrics (rank/%rostered)
    # accrue on their own schedule and must show even on dates with no sentiment point.
    sent_by_t = {
        r["t"].date().isoformat(): (
            round(float(r["s"]), 3),
            round(float(r["c"]), 1) if r["c"] is not None else None,
        )
        for r in s_rows
    }
    market_by_t = {
        r["t"].date().isoformat(): (
            round(float(r["a"]), 1) if r["a"] is not None else None,
            round(float(r["r"]), 1) if r["r"] is not None else None,
            round(float(r["pr"]), 1) if r["pr"] is not None else None,
        )
        for r in a_rows
    }

    points = []
    for t in sorted(set(sent_by_t) | set(market_by_t)):
        sentiment, concern = sent_by_t.get(t, (None, None))
        adp, rank, rostered = market_by_t.get(t, (None, None, None))
        points.append({
            "t": t,
            "sentiment": sentiment,
            "concern": concern,
            "adp": adp,
            "rank": rank,
            "rostered": rostered,
        })

    return {
        "player_id": player_id,
        "range": rng,
        "points": points,
        "count": len(points),
    }


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
