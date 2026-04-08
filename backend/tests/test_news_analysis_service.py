"""
Tests for Phase 4.5 — News Analyzer.
Covers: rule_filter_service, news_queue_service, news_analysis_service (mocked Gemini),
        and the /api/news router (TestClient).

Usage: python3 tests/test_news_analysis_service.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Rule Filter
# ══════════════════════════════════════════════════════════════════════════════

def run_rule_filter_tests():
    from services.rule_filter_service import apply_rule_filter, should_run_gemini

    print("=" * 50)
    print("RULE FILTER — UNIT TESTS")
    print("=" * 50)

    # [1] BEARISH HIGH — ruled out
    print("\n[1] 'ruled out' → BEARISH/HIGH...")
    r = apply_rule_filter("Ja'Marr Chase ruled out Sunday", None, "regular")
    assert r.matched
    assert r.direction == "BEARISH"
    assert r.magnitude == "HIGH"
    assert r.confidence == 0.95
    print(f"    PASS — {r.direction}/{r.magnitude} conf={r.confidence}")

    # [2] BEARISH HIGH — torn
    print("\n[2] 'torn ACL' → BEARISH/HIGH...")
    r = apply_rule_filter("Player tears ACL", "Season-ending injury confirmed", "regular")
    assert r.matched
    assert r.direction == "BEARISH"
    assert r.magnitude == "HIGH"
    print(f"    PASS — {r.direction}/{r.magnitude}")

    # [3] BULLISH HIGH — activated from IR
    print("\n[3] 'activated from IR' → BULLISH/HIGH...")
    r = apply_rule_filter("Christian McCaffrey activated from IR", None, "regular")
    assert r.matched
    assert r.direction == "BULLISH"
    assert r.magnitude == "HIGH"
    print(f"    PASS — {r.direction}/{r.magnitude}")

    # [4] NEUTRAL LOW — veteran day off
    print("\n[4] 'veteran day off' → NEUTRAL/LOW...")
    r = apply_rule_filter("Davante Adams given veteran day off Wednesday", None, "regular")
    assert r.matched
    assert r.direction == "NEUTRAL"
    assert r.magnitude == "LOW"
    print(f"    PASS — {r.direction}/{r.magnitude}")

    # [5] No match → should pass to Gemini (in-season)
    print("\n[5] Unmatched news (in-season) → Gemini=True for starred...")
    r = apply_rule_filter("Tyreek Hill had a great practice today", None, "regular")
    assert not r.matched
    result = should_run_gemini(r, is_starred=True, season_type="regular")
    assert result is True
    print(f"    PASS — matched={r.matched}, gemini={result}")

    # [6] Rostered-only → never Gemini
    print("\n[6] Rostered-only player → Gemini=False regardless...")
    r = apply_rule_filter("Player injured in practice", None, "regular")
    result = should_run_gemini(r, is_starred=False, season_type="regular")
    assert result is False
    print(f"    PASS — gemini={result}")

    # [7] Offseason + significant keyword → Gemini allowed for starred
    # Use a trade-adjacent headline that doesn't match any rule pattern exactly
    print("\n[7] Offseason + trade rumors → Gemini=True for starred...")
    r = apply_rule_filter("Cooper Kupp trade rumors heating up", None, "off")
    result = should_run_gemini(r, is_starred=True, season_type="off")
    assert not r.matched, "Expected no rule match for trade rumors headline"
    assert result is True, f"Expected Gemini=True for offseason trade news, got {result}"
    print(f"    PASS — offseason_significant={r.offseason_significant}, gemini={result}")

    # [8] Offseason + routine noise → Gemini=False for starred
    print("\n[8] Offseason + OTA mention → Gemini=False for starred...")
    r = apply_rule_filter("CeeDee Lamb looks good in OTAs", None, "off")
    result = should_run_gemini(r, is_starred=True, season_type="off")
    # rule matched as NEUTRAL/LOW → should_run_gemini returns False (rule matched)
    assert result is False
    print(f"    PASS — matched={r.matched}, gemini={result}")

    print("\n✅ All rule filter tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Queue Service
# ══════════════════════════════════════════════════════════════════════════════

def run_queue_tests():
    from services.news_queue_service import NewsAnalysisQueue, QueuedItem

    print("\n" + "=" * 50)
    print("NEWS QUEUE — UNIT TESTS")
    print("=" * 50)

    queue = NewsAnalysisQueue()

    # [1] Fresh queue allows calls
    print("\n[1] Fresh queue — can_call=True...")
    assert queue.can_call()
    assert queue.calls_remaining() == 10
    print(f"    PASS — calls_remaining={queue.calls_remaining()}")

    # [2] Fill up the window
    print("\n[2] Fill window to limit...")
    for i in range(10):
        queue.record_call()
    assert not queue.can_call()
    assert queue.calls_remaining() == 0
    print(f"    PASS — can_call={queue.can_call()} remaining={queue.calls_remaining()}")

    # [3] Dequeue returns None when rate-limited
    print("\n[3] Dequeue while rate-limited → None...")
    queue.enqueue(QueuedItem(news_id=99, player_id="p1", player_name="Test Player", is_starred=True))
    item = queue.dequeue()
    assert item is None
    print(f"    PASS — dequeue returned None under rate limit")

    # [4] Priority — starred before rostered-only
    print("\n[4] Priority ordering — starred first...")
    queue2 = NewsAnalysisQueue()
    queue2.enqueue(QueuedItem(news_id=1, player_id="p_rostered", player_name="Rostered", is_starred=False))
    queue2.enqueue(QueuedItem(news_id=2, player_id="p_starred", player_name="Starred", is_starred=True))
    first = queue2.dequeue()
    assert first is not None
    assert first.is_starred is True, f"Expected starred first, got is_starred={first.is_starred}"
    print(f"    PASS — first dequeued: {first.player_name} (starred={first.is_starred})")

    # [5] Duplicate prevention
    print("\n[5] Duplicate news_id rejected...")
    queue3 = NewsAnalysisQueue()
    added1 = queue3.enqueue(QueuedItem(news_id=42, player_id="p1", player_name="P1", is_starred=True))
    added2 = queue3.enqueue(QueuedItem(news_id=42, player_id="p1", player_name="P1", is_starred=True))
    assert added1 is True
    assert added2 is False
    assert queue3.pending_count() == 1
    print(f"    PASS — duplicate rejected, queue depth={queue3.pending_count()}")

    print("\n✅ All queue tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — News Analysis Service (mocked Gemini)
# ══════════════════════════════════════════════════════════════════════════════

def run_analysis_service_tests():
    import asyncio
    from unittest.mock import AsyncMock, patch, MagicMock

    print("\n" + "=" * 50)
    print("NEWS ANALYSIS SERVICE — UNIT TESTS (mocked Gemini)")
    print("=" * 50)

    async def _test():
        from services.news_analysis_service import analyze_news_item
        from models.news import PlayerNews

        # Fake news item
        news_item = MagicMock(spec=PlayerNews)
        news_item.id = 1
        news_item.player_id = "player123"
        news_item.headline = "Patrick Mahomes ruled out Sunday"
        news_item.news_body = "Mahomes suffered an ankle injury in practice."

        player_context = {
            "player_name": "Patrick Mahomes",
            "position": "QB",
            "nfl_team": "KC",
            "weighted_proj": 28.5,
            "trending_status": "Trending adds",
            "stats_context": "24.2 avg PPR last 3 weeks",
        }

        pass1_response = {
            "summary": "Mahomes ruled out. Big blow for fantasy managers.",
            "news_type": "INJURY",
            "stock_direction": "BEARISH",
            "stock_magnitude": "HIGH",
            "short_term_impact": "Stream or sit Week X",
            "long_term_impact": None,
            "key_factors": ["ruled out", "ankle injury"],
            "confidence_score": 0.95,
            "needs_context_check": False,
        }

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_db.flush = AsyncMock()
        mock_db.add = MagicMock()  # Session.add() is sync — not a coroutine

        with patch(
            "services.news_analysis_service._call_gemini",
            new=AsyncMock(return_value=pass1_response)
        ), patch(
            "services.news_analysis_service._call_gemini_text",
            new=AsyncMock(return_value="Context summary placeholder")
        ):
            result = await analyze_news_item(news_item, player_context, mock_db)

        assert result is not None, "Expected a NewsAnalysis result"
        assert result.stock_direction == "BEARISH"
        assert result.stock_magnitude == "HIGH"
        assert result.confidence_score == 0.95
        assert result.contradictions_flagged is False
        print("\n[1] PASS — Pass 1 BEARISH/HIGH with no context check")

        # [2] HIGH magnitude blocked when confidence < 0.75
        print("\n[2] HIGH magnitude blocked at confidence=0.60...")
        low_conf_response = {**pass1_response, "stock_magnitude": "HIGH", "confidence_score": 0.60}
        with patch(
            "services.news_analysis_service._call_gemini",
            new=AsyncMock(return_value=low_conf_response)
        ), patch(
            "services.news_analysis_service._call_gemini_text",
            new=AsyncMock(return_value="summary")
        ):
            result2 = await analyze_news_item(news_item, player_context, mock_db)

        assert result2 is not None
        assert result2.stock_magnitude == "MEDIUM", \
            f"Expected MEDIUM (downgraded from HIGH), got {result2.stock_magnitude}"
        print(f"    PASS — magnitude downgraded to {result2.stock_magnitude}")

        # [3] needs_context_check=True triggers Pass 2
        print("\n[3] needs_context_check=True → Pass 2 fires...")
        needs_check_response = {**pass1_response, "needs_context_check": True, "confidence_score": 0.80}
        pass2_response = {
            "context_notes": "Prior report said he'd play — contradiction.",
            "contradictions_flagged": True,
            "contradiction_detail": "Monday practice report said full participant.",
            "final_confidence": 0.85,
        }

        mock_db2 = AsyncMock()
        mock_db2.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=MagicMock(context_summary="Prior: Mahomes practiced fully Monday."))
        ))
        mock_db2.flush = AsyncMock()
        mock_db2.add = MagicMock()  # Session.add() is sync

        call_count = {"n": 0}
        async def _mock_gemini(prompt, model):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return needs_check_response
            return pass2_response

        with patch("services.news_analysis_service._call_gemini", new=_mock_gemini), \
             patch("services.news_analysis_service._call_gemini_text", new=AsyncMock(return_value="summary")):
            result3 = await analyze_news_item(news_item, player_context, mock_db2)

        assert result3 is not None
        assert result3.contradictions_flagged is True
        assert result3.contradiction_detail is not None
        assert call_count["n"] == 2, f"Expected 2 Gemini calls (Pass 1 + Pass 2), got {call_count['n']}"
        print(f"    PASS — contradictions_flagged={result3.contradictions_flagged}, calls={call_count['n']}")

    asyncio.run(_test())
    print("\n✅ All news analysis service tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — /api/news router (TestClient)
# ══════════════════════════════════════════════════════════════════════════════

def run_router_tests():
    from unittest.mock import AsyncMock, patch, MagicMock
    from fastapi.testclient import TestClient
    from main import app

    print("\n" + "=" * 50)
    print("/api/news ROUTER — INTEGRATION TESTS (mocked scraper)")
    print("=" * 50)

    mock_scrape_summary = {
        "new_items": 3,
        "skipped_dedup": 1,
        "skipped_untracked": 5,
        "rule_filtered": 2,
        "gemini_ran": 1,
        "gemini_queue_remaining": 0,
        "queue_status": {"calls_in_window": 1, "calls_remaining": 9, "pending_items": 0, "window_resets_at": None},
    }

    # Both requests share one TestClient — keeps one event loop alive across calls
    with patch(
        "routers.news.scrape_and_analyze",
        new=AsyncMock(return_value=mock_scrape_summary)
    ), patch(
        "routers.news.get_nfl_state",
        new=AsyncMock(return_value={"season_type": "off", "week": 1, "season": 2025})
    ):
        with TestClient(app) as client:
            # [1] GET /api/news returns 200 with expected structure
            print("\n[1] GET /api/news returns 200 with expected keys...")
            resp = client.get("/api/news")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "news" in data
            assert "total" in data
            assert "season_type" in data
            assert "scrape_summary" in data
            print(f"    PASS — status=200, total={data['total']}, season_type={data['season_type']}")

            # [2] force_refresh=true is accepted
            print("\n[2] GET /api/news?force_refresh=true returns 200...")
            resp = client.get("/api/news?force_refresh=true")
            assert resp.status_code == 200
            print(f"    PASS — force_refresh accepted")

    print("\n✅ All router tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_rule_filter_tests()
    run_queue_tests()
    run_analysis_service_tests()
    run_router_tests()
    print("\n" + "=" * 50)
    print("ALL PHASE 4.5 TESTS PASSED ✅")
    print("=" * 50)
