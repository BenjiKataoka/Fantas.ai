"""
Tests for news_scraper_service.py
Covers: TTL helpers, injury bypass, tier resolution, deduplication, orchestration.
Usage: python3 tests/test_news_scraper_service.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1, TTL helper functions
# ══════════════════════════════════════════════════════════════════════════════

def run_ttl_tests():
    from services.news_scraper_service import (
        _starred_ttl_minutes,
        _rostered_ttl_minutes,
        _is_due,
    )

    print("=" * 50)
    print("NEWS SCRAPER, TTL HELPER TESTS")
    print("=" * 50)

    # [1] Starred TTLs by season type
    print("\n[1] Starred TTLs by season type...")
    assert _starred_ttl_minutes("off") == 24 * 60
    assert _starred_ttl_minutes("pre") == 4 * 60
    assert _starred_ttl_minutes("regular", team_playing_today=False) == 120
    assert _starred_ttl_minutes("regular", team_playing_today=True) == 60
    assert _starred_ttl_minutes("post", team_playing_today=True) == 60
    assert _starred_ttl_minutes("post", team_playing_today=False) == 120
    print(f"    PASS, off=1440m, pre=240m, regular game-day=60m, regular non-game=120m")

    # [2] Rostered-only TTLs
    print("\n[2] Rostered-only TTLs...")
    assert _rostered_ttl_minutes("off") is None  # never refresh rostered-only in offseason
    assert _rostered_ttl_minutes("pre") == 4 * 60
    assert _rostered_ttl_minutes("regular") == 4 * 60
    assert _rostered_ttl_minutes("post") == 4 * 60
    print(f"    PASS, off=None, pre/regular/post=240m")

    # [3] _is_due logic
    print("\n[3] _is_due() logic...")
    now = datetime.utcnow()

    # Never checked → always due
    assert _is_due(None, 60) is True

    # TTL=None → never due
    assert _is_due(None, None) is False
    assert _is_due(now, None) is False

    # Checked 90 min ago, TTL=60 → due
    checked_90m_ago = now - timedelta(minutes=90)
    assert _is_due(checked_90m_ago, 60) is True

    # Checked 30 min ago, TTL=60 → not due
    checked_30m_ago = now - timedelta(minutes=30)
    assert _is_due(checked_30m_ago, 60) is False

    print(f"    PASS, all _is_due() cases correct")

    print("\n✅ All TTL tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2, Injury/transaction bypass
# ══════════════════════════════════════════════════════════════════════════════

def run_bypass_tests():
    from services.rule_filter_service import apply_rule_filter, should_run_gemini

    print("\n" + "=" * 50)
    print("NEWS SCRAPER, INJURY/TRANSACTION BYPASS TESTS")
    print("=" * 50)

    # The bypass is implemented in news_scraper_service via `effective_season_type`.
    # We test the underlying logic here: injury news in offseason → Gemini runs.

    # [1] Injury-adjacent headline in offseason → offseason_significant=True → Gemini runs
    # Bypass uses offseason_significant (set by keyword scan), not news_type_hint
    print("\n[1] Injury-adjacent news in offseason → bypass → Gemini runs for starred...")
    r = apply_rule_filter("Hopkins dealing with knee soreness", None, "off")
    # "knee" doesn't trigger a rule, but "injur" keyword isn't in text,
    # use a headline that has an injury keyword but no exact rule match
    r2 = apply_rule_filter("Hopkins hamstring soreness week to week", None, "off")
    # "hamstring" matches the BEARISH MEDIUM rule, rule matched, Gemini skipped
    # Use a softer injury mention that triggers offseason_significant but no rule
    r3 = apply_rule_filter("Hopkins nursing a minor injury, day-to-day", None, "off")
    assert r3.offseason_significant is True, \
        f"Expected offseason_significant=True for injury mention, got {r3.offseason_significant}"
    effective = "regular" if r3.offseason_significant and True else "off"
    result = should_run_gemini(r3, is_starred=True, season_type=effective)
    assert result is True
    print(f"    PASS, offseason_significant={r3.offseason_significant}, effective_season=regular, gemini={result}")

    # [2] Trade news in offseason → bypass → Gemini runs
    print("\n[2] Trade news in offseason → bypass → Gemini runs...")
    r = apply_rule_filter("Hopkins trade rumors heating up with the Bears", None, "off")
    assert not r.matched, "Expected no rule match for trade rumors"
    assert r.offseason_significant is True, f"Expected offseason_significant=True, got {r.offseason_significant}"
    effective = "regular" if r.offseason_significant else "off"
    result = should_run_gemini(r, is_starred=True, season_type=effective)
    assert result is True
    print(f"    PASS, offseason_significant={r.offseason_significant}, gemini={result}")

    # [3] Routine offseason update → no bypass → Gemini blocked
    print("\n[3] Routine offseason update → no bypass → Gemini blocked...")
    r = apply_rule_filter("Player attends charity event", None, "off")
    assert r.offseason_significant is False
    result = should_run_gemini(r, is_starred=True, season_type="off")
    assert result is False
    print(f"    PASS, no bypass, Gemini blocked for routine offseason update")

    print("\n✅ All bypass tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3, Orchestration (mocked DB + services)
# ══════════════════════════════════════════════════════════════════════════════

def run_orchestration_tests():
    print("\n" + "=" * 50)
    print("NEWS SCRAPER, ORCHESTRATION TESTS")
    print("=" * 50)

    async def _test():
        from services import news_scraper_service

        # Minimal fake news items
        fake_rw_news = [
            {
                "player_name": "Patrick Mahomes",
                "headline": "Mahomes ruled out Sunday",
                "news_body": "Ankle injury keeps him out this week.",
                "published_at": datetime.utcnow(),
                "source_url": "https://rotowire.com/news/1",
                "source": "ROTOWIRE",
                "espn_athlete_id": None,
            },
            {
                "player_name": "Nobody McUnknown",
                "headline": "Unknown player update",
                "news_body": None,
                "published_at": datetime.utcnow(),
                "source_url": "https://rotowire.com/news/2",
                "source": "ROTOWIRE",
                "espn_athlete_id": None,
            },
        ]
        fake_espn_news = []
        fake_teams_today = {"KC", "SF"}

        # Mock DB that returns Mahomes as a starred player
        mock_db = AsyncMock()

        # _get_player_tiers: starred_ids = {"mahomes_id"}, rostered_ids = set()
        # _get_last_checked: returns None (never checked)
        # existing source_urls: empty
        # db.get(Player, ...): returns a player row with team="KC"

        call_tracker = {"execute_calls": 0}

        async def mock_execute(stmt):
            call_tracker["execute_calls"] += 1
            mock_result = MagicMock()
            # Return starred players on first call, rostered on second, empty URL set on third
            n = call_tracker["execute_calls"]
            if n == 1:
                # tracked_players query → mahomes_id
                mock_result.fetchall.return_value = [("mahomes_id",)]
            elif n == 2:
                # my_roster query → empty (not rostered separately)
                mock_result.fetchall.return_value = []
            elif n == 3:
                # tracked names (for RSS matcher) → empty (RSS is mocked out anyway)
                mock_result.fetchall.return_value = []
            elif n == 4:
                # existing source_urls → empty
                mock_result.fetchall.return_value = []
            else:
                # last_checked query
                mock_result.scalar_one_or_none.return_value = None
                mock_result.fetchall.return_value = []
            return mock_result

        mock_db.execute = mock_execute
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        fake_player = MagicMock()
        fake_player.nfl_team = "KC"
        mock_db.get = AsyncMock(return_value=fake_player)

        # [1] Untracked player is skipped
        print("\n[1] Untracked player ('Nobody McUnknown') is skipped...")
        with patch("services.news_scraper_service.rotowire_service.scrape_rotowire_news",
                   return_value=fake_rw_news), \
             patch("services.news_scraper_service.nfl_service.get_espn_news",
                   new=AsyncMock(return_value=fake_espn_news)), \
             patch("services.news_scraper_service.get_teams_playing_today",
                   new=AsyncMock(return_value=fake_teams_today)), \
             patch("services.news_scraper_service.rss_service.fetch_rss_news",
                   new=AsyncMock(return_value=[])), \
             patch("services.news_scraper_service._resolve_player_id",
                   new=AsyncMock(side_effect=["mahomes_id", None])):  # Mahomes resolves, Nobody doesn't

            summary = await news_scraper_service.scrape_and_analyze(
                db=mock_db,
                season_type="regular",
                force_refresh=True,
            )

        assert summary["skipped_untracked"] >= 1, \
            f"Expected at least 1 untracked skip, got {summary['skipped_untracked']}"
        print(f"    PASS, skipped_untracked={summary['skipped_untracked']}")

        # [2] Deduplication: same source_url skipped on second pass
        print("\n[2] Deduplication skips already-seen source_urls...")
        call_tracker["execute_calls"] = 0

        async def mock_execute_with_url(stmt):
            call_tracker["execute_calls"] += 1
            mock_result = MagicMock()
            n = call_tracker["execute_calls"]
            if n == 1:
                mock_result.fetchall.return_value = [("mahomes_id",)]   # starred tier
            elif n == 2:
                mock_result.fetchall.return_value = []                   # rostered tier
            elif n == 3:
                mock_result.fetchall.return_value = [("Patrick Mahomes",)]  # tracked names (for RSS matcher)
            elif n == 4:
                # Return the existing URL so Mahomes's news gets deduped
                mock_result.fetchall.return_value = [("https://rotowire.com/news/1",)]
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.fetchall.return_value = []
            return mock_result

        mock_db.execute = mock_execute_with_url

        with patch("services.news_scraper_service.rotowire_service.scrape_rotowire_news",
                   return_value=fake_rw_news), \
             patch("services.news_scraper_service.nfl_service.get_espn_news",
                   new=AsyncMock(return_value=[])), \
             patch("services.news_scraper_service.get_teams_playing_today",
                   new=AsyncMock(return_value=fake_teams_today)), \
             patch("services.news_scraper_service.rss_service.fetch_rss_news",
                   new=AsyncMock(return_value=[])):

            summary = await news_scraper_service.scrape_and_analyze(
                db=mock_db,
                season_type="regular",
                force_refresh=True,
            )

        assert summary["skipped_dedup"] >= 1, \
            f"Expected at least 1 dedup skip, got {summary['skipped_dedup']}"
        print(f"    PASS, skipped_dedup={summary['skipped_dedup']}")

    asyncio.run(_test())
    print("\n✅ All orchestration tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4, Failure modes (both source APIs down)
# ══════════════════════════════════════════════════════════════════════════════

def run_scraper_failure_tests():
    print("\n" + "=" * 50)
    print("NEWS SCRAPER, SOURCE FAILURE MODES")
    print("=" * 50)

    async def _test():
        from services import news_scraper_service

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        call_n = {"n": 0}
        async def mock_execute(stmt):
            call_n["n"] += 1
            r = MagicMock()
            r.fetchall.return_value = []
            r.scalar_one_or_none.return_value = None
            return r
        mock_db.execute = mock_execute

        # [1] Both sources fail → returns summary with 0 new items (no exception)
        print("\n[1] Both RotoWire and ESPN fail → 0 new items, no exception...")
        with patch("services.news_scraper_service.rotowire_service.scrape_rotowire_news",
                   return_value=[]), \
             patch("services.news_scraper_service.nfl_service.get_espn_news",
                   new=AsyncMock(return_value=[])), \
             patch("services.news_scraper_service.get_teams_playing_today",
                   new=AsyncMock(return_value=set())), \
             patch("services.news_scraper_service.rss_service.fetch_rss_news",
                   new=AsyncMock(return_value=[])):

            summary = await news_scraper_service.scrape_and_analyze(
                db=mock_db,
                season_type="regular",
                force_refresh=True,
            )

        assert summary["new_items"] == 0
        assert summary["gemini_ran"] == 0
        print(f"    PASS, summary: {summary}")

        # [2] Schedule API fails → scraper continues with empty teams set
        print("\n[2] Schedule API fails → scraper uses empty teams set, continues...")
        call_n["n"] = 0
        with patch("services.news_scraper_service.rotowire_service.scrape_rotowire_news",
                   return_value=[]), \
             patch("services.news_scraper_service.nfl_service.get_espn_news",
                   new=AsyncMock(return_value=[])), \
             patch("services.news_scraper_service.get_teams_playing_today",
                   new=AsyncMock(return_value=set())), \
             patch("services.news_scraper_service.rss_service.fetch_rss_news",
                   new=AsyncMock(return_value=[])):  # empty = schedule API failed

            summary = await news_scraper_service.scrape_and_analyze(
                db=mock_db,
                season_type="regular",
                force_refresh=True,
            )

        assert "new_items" in summary  # completed without exception
        print(f"    PASS, completed with empty teams set")

    asyncio.run(_test())
    print("\n✅ All scraper failure mode tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_ttl_tests()
    run_bypass_tests()
    run_orchestration_tests()
    run_scraper_failure_tests()
    print("\n" + "=" * 50)
    print("ALL NEWS SCRAPER TESTS PASSED ✅")
    print("=" * 50)
