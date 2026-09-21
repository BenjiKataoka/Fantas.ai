"""
Tests for Phase 4.6, Player Tracker.
Covers: ADP trend calc, star/unstar, tracker list, router endpoints, failure modes.
Usage: python3 tests/test_tracker_service.py
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1, ADP trend calculation
# ══════════════════════════════════════════════════════════════════════════════

def run_adp_trend_tests():
    print("=" * 50)
    print("TRACKER, ADP TREND TESTS")
    print("=" * 50)

    async def _test():
        from services.adp_service import compute_adp_trend

        mock_db = AsyncMock()
        now = datetime.utcnow()

        # [1] RISING, ADP improved by > 2 positions (lower number = better)
        print("\n[1] RISING trend, ADP moved from 30 to 25...")
        recent_rows = [MagicMock(adp=24.0), MagicMock(adp=26.0)]  # avg 25
        old_rows = [MagicMock(adp=29.0), MagicMock(adp=31.0)]    # avg 30

        async def mock_execute_rising(stmt):
            r = MagicMock()
            if not hasattr(mock_execute_rising, "call_count"):
                mock_execute_rising.call_count = 0
            mock_execute_rising.call_count += 1
            r.scalars.return_value.all.return_value = (
                recent_rows if mock_execute_rising.call_count == 1 else old_rows
            )
            return r

        mock_db.execute = mock_execute_rising
        result = await compute_adp_trend("player1", mock_db)
        assert result["trend"] == "RISING", f"Expected RISING, got {result['trend']}"
        assert result["delta"] < -2, f"Expected delta < -2, got {result['delta']}"
        print(f"    PASS, trend=RISING, delta={result['delta']}")

        # [2] FALLING, ADP worsened by > 2 positions
        print("\n[2] FALLING trend, ADP moved from 20 to 26...")
        recent_rows2 = [MagicMock(adp=25.0), MagicMock(adp=27.0)]  # avg 26
        old_rows2 = [MagicMock(adp=19.0), MagicMock(adp=21.0)]      # avg 20

        call_count = {"n": 0}
        async def mock_execute_falling(stmt):
            r = MagicMock()
            call_count["n"] += 1
            r.scalars.return_value.all.return_value = (
                recent_rows2 if call_count["n"] == 1 else old_rows2
            )
            return r

        mock_db.execute = mock_execute_falling
        result = await compute_adp_trend("player2", mock_db)
        assert result["trend"] == "FALLING", f"Expected FALLING, got {result['trend']}"
        assert result["delta"] > 2, f"Expected delta > 2, got {result['delta']}"
        print(f"    PASS, trend=FALLING, delta={result['delta']}")

        # [3] STABLE, within ±2 positions
        print("\n[3] STABLE trend, ADP within 2 positions...")
        recent_rows3 = [MagicMock(adp=15.0)]
        old_rows3 = [MagicMock(adp=15.5)]

        count3 = {"n": 0}
        async def mock_execute_stable(stmt):
            r = MagicMock()
            count3["n"] += 1
            r.scalars.return_value.all.return_value = (
                recent_rows3 if count3["n"] == 1 else old_rows3
            )
            return r

        mock_db.execute = mock_execute_stable
        result = await compute_adp_trend("player3", mock_db)
        assert result["trend"] == "STABLE", f"Expected STABLE, got {result['trend']}"
        print(f"    PASS, trend=STABLE, delta={result['delta']}")

        # [4] Insufficient data → STABLE default
        print("\n[4] Insufficient data → STABLE with no crash...")
        async def mock_execute_empty(stmt):
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            return r

        mock_db.execute = mock_execute_empty
        result = await compute_adp_trend("player4", mock_db)
        assert result["trend"] == "STABLE"
        assert result["today_avg"] is None
        print(f"    PASS, empty data returns STABLE gracefully")

    asyncio.run(_test())
    print("\n✅ All ADP trend tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2, Star / Unstar
# ══════════════════════════════════════════════════════════════════════════════

def run_star_unstar_tests():
    print("\n" + "=" * 50)
    print("TRACKER, STAR / UNSTAR TESTS")
    print("=" * 50)

    async def _test():
        from services import tracker_service

        # [1] Star a new player
        print("\n[1] Star a new player...")
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        fake_player = MagicMock()
        fake_player.name = "Justin Jefferson"
        fake_player.position = "WR"
        fake_player.nfl_team = "MIN"

        # db.get returns None for TrackedPlayer (not starred yet), returns player for Player
        async def mock_get(model, key):
            from models.tracker import TrackedPlayer
            from models.player import Player
            if model is TrackedPlayer:
                return None
            if model is Player:
                return fake_player
            return None

        mock_db.get = mock_get

        def _close_coro(coro):
            coro.close()  # prevent "coroutine never awaited" warning in tests
            return MagicMock()

        with patch("services.tracker_service.asyncio.create_task", side_effect=_close_coro):
            result = await tracker_service.star_player(1, "jj_id", mock_db)

        assert result["status"] == "starred", f"Expected starred, got {result}"
        assert mock_db.add.called
        print(f"    PASS, {result}")

        # [2] Star already-starred player
        print("\n[2] Already-starred player returns 'already_starred'...")
        existing = MagicMock()
        existing.is_active = True

        async def mock_get_existing(model, key):
            from models.tracker import TrackedPlayer
            if model is TrackedPlayer:
                return existing
            return fake_player

        mock_db.get = mock_get_existing
        result = await tracker_service.star_player(1, "jj_id", mock_db)
        assert result["status"] == "already_starred"
        print(f"    PASS, {result}")

        # [3] Unstar an active player
        print("\n[3] Unstar an active player...")
        active_tracked = MagicMock()
        active_tracked.is_active = True

        async def mock_get_tracked(model, key):
            from models.tracker import TrackedPlayer
            if model is TrackedPlayer:
                return active_tracked
            return None

        mock_db.get = mock_get_tracked
        result = await tracker_service.unstar_player(1, "jj_id", mock_db)
        assert result["status"] == "unstarred"
        assert active_tracked.is_active is False
        print(f"    PASS, {result}")

        # [4] Unstar player not in tracker
        print("\n[4] Unstar player not in tracker → 'not_found'...")
        async def mock_get_none(model, key):
            return None

        mock_db.get = mock_get_none
        result = await tracker_service.unstar_player(1, "nobody", mock_db)
        assert result["status"] == "not_found"
        print(f"    PASS, {result}")

    asyncio.run(_test())
    print("\n✅ All star/unstar tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3, Combined score formula
# ══════════════════════════════════════════════════════════════════════════════

def run_combined_score_tests():
    print("\n" + "=" * 50)
    print("TRACKER, COMBINED SCORE FORMULA TESTS")
    print("=" * 50)

    from services.sentiment_service import ADP_PENALTY

    # Formula: (concern_level × 0.50) + (worry_score × 0.30) + (adp_penalty × 0.20)
    # [1] Worst case: concern=10, worry=10, FALLING (+2)
    print("\n[1] Worst-case: concern=10, worry=10, FALLING...")
    score = (10 * 0.50) + (10 * 0.30) + (ADP_PENALTY["FALLING"] * 0.20)
    assert score == 8.4, f"Expected 8.4, got {score}"
    print(f"    PASS, combined_score={score}")

    # [2] Best case: concern=1, worry=1, RISING (-1)
    print("\n[2] Best-case: concern=1, worry=1, RISING...")
    score = round((1 * 0.50) + (1 * 0.30) + (ADP_PENALTY["RISING"] * 0.20), 2)
    assert score == 0.6, f"Expected 0.6, got {score}"
    print(f"    PASS, combined_score={score}")

    # [3] Neutral: concern=5, worry=5, STABLE
    print("\n[3] Neutral: concern=5, worry=5, STABLE...")
    score = (5 * 0.50) + (5 * 0.30) + (ADP_PENALTY["STABLE"] * 0.20)
    assert score == 4.0, f"Expected 4.0, got {score}"
    print(f"    PASS, combined_score={score}")

    print("\n✅ All combined score tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4, Router endpoints
# ══════════════════════════════════════════════════════════════════════════════

def run_router_tests():
    print("\n" + "=" * 50)
    print("TRACKER, ROUTER TESTS")
    print("=" * 50)

    from fastapi.testclient import TestClient
    from main import app
    from auth import get_current_user

    # Fixed authenticated user so auth doesn't consult the (unmocked) DB in these tests.
    fake_user = MagicMock(id=1, is_approved=True, clerk_id="test")
    app.dependency_overrides[get_current_user] = lambda: fake_user

    with TestClient(app) as client:

        # [1] GET /api/tracker, returns list (empty is fine)
        print("\n[1] GET /api/tracker returns 200...")
        with patch("routers.tracker.tracker_service.get_tracked_players",
                   new=AsyncMock(return_value=[])):
            resp = client.get("/api/tracker")
        assert resp.status_code == 200
        data = resp.json()
        assert "tracked_players" in data
        assert "total" in data
        print(f"    PASS, status=200, total={data['total']}")

        # [2] GET /api/tracker/{player_id}, not found returns 404
        print("\n[2] GET /api/tracker/unknown returns 404...")
        with patch("routers.tracker.tracker_service.get_tracked_player_detail",
                   new=AsyncMock(return_value=None)):
            resp = client.get("/api/tracker/unknown_player_id")
        assert resp.status_code == 404
        print(f"    PASS, 404 for untracked player")

        # [3] POST /api/tracker/star/{player_id}, success
        print("\n[3] POST /api/tracker/star/test_player_id returns 200...")
        with patch("routers.tracker.tracker_service.star_player",
                   new=AsyncMock(return_value={"status": "starred", "player_id": "test_id"})):
            resp = client.post("/api/tracker/star/test_player_id")
        assert resp.status_code == 200
        assert resp.json()["status"] == "starred"
        print(f"    PASS, star returned {resp.json()}")

        # [4] DELETE /api/tracker/star/{player_id}, not found returns 404
        print("\n[4] DELETE /api/tracker/star/unknown returns 404...")
        with patch("routers.tracker.tracker_service.unstar_player",
                   new=AsyncMock(return_value={"status": "not_found"})):
            resp = client.delete("/api/tracker/star/unknown")
        assert resp.status_code == 404
        print(f"    PASS, 404 for unstarred player")

        # [5] POST /api/tracker/refresh/{player_id}, success
        print("\n[5] POST /api/tracker/refresh/test_id returns 200...")
        with patch("routers.tracker.tracker_service.refresh_profile",
                   new=AsyncMock(return_value=True)):
            resp = client.post("/api/tracker/refresh/test_player_id")
        assert resp.status_code == 200
        assert resp.json()["status"] == "refresh_triggered"
        print(f"    PASS, refresh returned {resp.json()}")

        # [6] POST /api/tracker/analyze-roster, kicks off batch, returns counts
        print("\n[6] POST /api/tracker/analyze-roster returns queued counts...")
        with patch("routers.tracker.tracker_service.analyze_roster",
                   new=AsyncMock(return_value={"status": "started", "queued": 12,
                                               "skipped_fresh": 3, "total": 15})):
            resp = client.post("/api/tracker/analyze-roster")
        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] == 12 and body["total"] == 15
        print(f"    PASS, analyze-roster returned {body}")

        # [7] GET /api/tracker/roster-analysis, static path not shadowed by {player_id}
        print("\n[7] GET /api/tracker/roster-analysis returns progress...")
        with patch("routers.tracker.tracker_service.roster_analysis_status",
                   new=AsyncMock(return_value={"total": 15, "ready": 9, "pending": 6})):
            resp = client.get("/api/tracker/roster-analysis")
        assert resp.status_code == 200, f"static route shadowed? got {resp.status_code}"
        assert resp.json()["ready"] == 9
        print(f"    PASS, roster-analysis returned {resp.json()}")

        # [8] GET /api/tracker/{id}/sentiment-history, chart series, range validated
        print("\n[8] GET /api/tracker/{id}/sentiment-history returns series...")
        with patch("routers.tracker.tracker_service.get_sentiment_history",
                   new=AsyncMock(return_value={"player_id": "4034", "range": "1m",
                                               "points": [{"t": "2026-09-01", "sentiment": 0.3, "concern": 4.0}],
                                               "latest": 0.3, "delta": 0.1, "count": 1})):
            resp = client.get("/api/tracker/4034/sentiment-history?range=1m")
        assert resp.status_code == 200, f"got {resp.status_code}"
        assert resp.json()["range"] == "1m" and resp.json()["count"] == 1
        # bad range rejected by the route's pattern validation
        resp_bad = client.get("/api/tracker/4034/sentiment-history?range=decade")
        assert resp_bad.status_code == 422, f"bad range should 422, got {resp_bad.status_code}"
        print("    PASS, series returned; invalid range rejected (422)")

    app.dependency_overrides.clear()
    print("\n✅ All router tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4.5, Batch roster analysis (freshness skip + queueing)
# ══════════════════════════════════════════════════════════════════════════════

def run_batch_analysis_tests():
    print("\n" + "=" * 50)
    print("TRACKER, BATCH ROSTER ANALYSIS")
    print("=" * 50)

    async def _test():
        from services import tracker_service

        def roster_of(*pids):
            result = MagicMock()
            result.scalars.return_value.all.return_value = list(pids)
            return result

        # [1] Mixed freshness: only stale/missing profiles get queued
        print("\n[1] Mixed freshness → fresh skipped, stale+missing queued...")
        fresh = MagicMock(last_full_analysis=datetime.utcnow())
        stale = MagicMock(last_full_analysis=datetime.utcnow() - timedelta(days=3))
        profiles = {"p1": fresh, "p2": stale, "p3": None}

        async def get_profile(model, pid):
            return profiles[pid]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=roster_of("p1", "p2", "p3"))
        mock_db.get = get_profile

        captured = {}
        async def fake_worker(user_id, player_ids):
            captured["ids"] = player_ids
            tracker_service._roster_runs.discard(user_id)  # mirror the real worker's cleanup

        with patch("services.tracker_service.get_nfl_state",
                   new=AsyncMock(return_value={"season_type": "regular"})), \
             patch("services.tracker_service._analyze_roster_worker", new=fake_worker):
            result = await tracker_service.analyze_roster(1, mock_db)
            await asyncio.sleep(0)  # let the fire-and-forget worker task run

        assert result == {"status": "started", "queued": 2, "skipped_fresh": 1, "total": 3}, result
        assert set(captured["ids"]) == {"p2", "p3"}, captured
        print(f"    PASS, {result}, queued ids={sorted(captured['ids'])}")

        # [2] All fresh → nothing queued, no worker spawned
        print("\n[2] All profiles fresh → all_fresh, queued=0...")
        profiles_all_fresh = {"p1": fresh, "p2": fresh}
        async def get_fresh(model, pid):
            return profiles_all_fresh[pid]
        mock_db2 = AsyncMock()
        mock_db2.execute = AsyncMock(return_value=roster_of("p1", "p2"))
        mock_db2.get = get_fresh
        spawned = {"called": False}
        async def worker_flag(user_id, player_ids):
            spawned["called"] = True
        with patch("services.tracker_service.get_nfl_state",
                   new=AsyncMock(return_value={"season_type": "regular"})), \
             patch("services.tracker_service._analyze_roster_worker", new=worker_flag):
            result = await tracker_service.analyze_roster(1, mock_db2)
            await asyncio.sleep(0)
        assert result["status"] == "all_fresh" and result["queued"] == 0, result
        assert spawned["called"] is False, "worker should not spawn when all fresh"
        print(f"    PASS, {result}")

        # [3] force=True re-queues even fresh players
        print("\n[3] force=True → all players queued despite fresh profiles...")
        mock_db3 = AsyncMock()
        mock_db3.execute = AsyncMock(return_value=roster_of("p1", "p2"))
        mock_db3.get = get_fresh
        cap3 = {}
        async def worker3(user_id, player_ids):
            cap3["ids"] = player_ids
            tracker_service._roster_runs.discard(user_id)
        with patch("services.tracker_service.get_nfl_state",
                   new=AsyncMock(return_value={"season_type": "regular"})), \
             patch("services.tracker_service._analyze_roster_worker", new=worker3):
            result = await tracker_service.analyze_roster(1, mock_db3, force=True)
            await asyncio.sleep(0)
        assert result["queued"] == 2 and result["skipped_fresh"] == 0, result
        print(f"    PASS, {result}")

        # [4] Empty roster → empty status, no crash
        print("\n[4] Empty roster → status=empty...")
        mock_db4 = AsyncMock()
        mock_db4.execute = AsyncMock(return_value=roster_of())
        result = await tracker_service.analyze_roster(1, mock_db4)
        assert result == {"status": "empty", "queued": 0, "skipped_fresh": 0, "total": 0}, result
        print(f"    PASS, {result}")

        # [5] Concurrency guard: a run already in flight → already_running, no 2nd worker
        print("\n[5] Run already in flight → already_running, no duplicate worker...")
        tracker_service._roster_runs.add(1)  # simulate an active run for user 1
        try:
            mock_db5 = AsyncMock()
            mock_db5.execute = AsyncMock(return_value=roster_of("p1", "p2"))
            mock_db5.get = get_fresh
            spawned5 = {"called": False}
            async def worker5(user_id, player_ids):
                spawned5["called"] = True
            with patch("services.tracker_service.get_nfl_state",
                       new=AsyncMock(return_value={"season_type": "regular"})), \
                 patch("services.tracker_service._analyze_roster_worker", new=worker5):
                result = await tracker_service.analyze_roster(1, mock_db5)
                await asyncio.sleep(0)
            assert result["status"] == "already_running", result
            assert spawned5["called"] is False, "must not spawn a second worker"
            print(f"    PASS, {result}")
        finally:
            tracker_service._roster_runs.discard(1)

    asyncio.run(_test())
    print("\n✅ All batch analysis tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4.6, Stock profile serializer (roster dropdown)
# ══════════════════════════════════════════════════════════════════════════════

def run_stock_serializer_tests():
    print("\n" + "=" * 50)
    print("TRACKER, STOCK PROFILE SERIALIZER")
    print("=" * 50)
    from services.tracker_service import serialize_stock_profile

    # [1] No profile / never completed → None (frontend shows "not analyzed yet")
    print("\n[1] None and unanalyzed profile → None...")
    assert serialize_stock_profile(None) is None
    unfinished = MagicMock(last_full_analysis=None)
    assert serialize_stock_profile(unfinished) is None
    print("    PASS, both return None")

    # [2] Completed profile → flat dict with key fields + ISO timestamp
    print("\n[2] Completed profile → serialized dict...")
    ts = datetime.utcnow()
    profile = MagicMock(
        last_full_analysis=ts, overall_direction="BULLISH", overall_magnitude="MEDIUM",
        concern_level=4, concern_summary="Workload trending up.", worry_score=3,
        combined_score=3.5, bullish_factors=["target share up"], bearish_factors=["tough schedule"],
        sentiment_score=0.42, sentiment_label="BULLISH", dominant_themes=["usage"],
        contrarian_flag=False, sentiment_vs_stock="CONFIRMS",
        short_term_outlook="Solid flex.", long_term_outlook="RB2 upside.",
        draft_recommendation="FAIR_VALUE",
    )
    out = serialize_stock_profile(profile)
    assert out["overall_direction"] == "BULLISH"
    assert out["concern_level"] == 4
    assert out["sentiment_score"] == 0.42
    assert out["last_full_analysis"] == ts.isoformat()
    assert "historical_context" not in out  # kept lean for roster payload
    print(f"    PASS, {out['overall_direction']}/{out['overall_magnitude']}, concern={out['concern_level']}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4.7, Sentiment history snapshot (append-only, for the graph)
# ══════════════════════════════════════════════════════════════════════════════

def run_sentiment_snapshot_tests():
    print("\n" + "=" * 50)
    print("TRACKER, SENTIMENT HISTORY SNAPSHOT")
    print("=" * 50)
    from services.tracker_service import _append_sentiment_snapshot
    from models.tracker import PlayerSentimentHistory

    # [1] Completed run → one history row added with the run's values
    print("\n[1] Completed analysis → snapshot row added...")
    db = MagicMock()
    result = {"sentiment_score": 0.42, "sentiment_label": "BULLISH", "concern_level": 3,
              "worry_score": 2, "combined_score": 2.4, "overall_direction": "BULLISH"}
    _append_sentiment_snapshot("p1", result, db)
    assert db.add.call_count == 1, "expected exactly one row added"
    row = db.add.call_args[0][0]
    assert isinstance(row, PlayerSentimentHistory)
    assert row.player_id == "p1" and row.sentiment_score == 0.42 and row.concern_level == 3
    print(f"    PASS, added sentiment={row.sentiment_score}, concern={row.concern_level}")

    # [2] Degraded run (null sentiment) → no row (would be a useless point)
    print("\n[2] Null sentiment_score → no snapshot written...")
    db2 = MagicMock()
    _append_sentiment_snapshot("p2", {"sentiment_score": None, "concern_level": 5}, db2)
    assert db2.add.call_count == 0, "must not write a null-sentiment point"
    print("    PASS, skipped degraded run")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4.8, Sentiment history query (graph endpoint)
# ══════════════════════════════════════════════════════════════════════════════

def run_sentiment_history_query_tests():
    print("\n" + "=" * 50)
    print("TRACKER, SENTIMENT HISTORY QUERY")
    print("=" * 50)

    class FakeResult:
        def __init__(self, rows): self._rows = rows
        def mappings(self): return self
        def all(self): return self._rows

    def db_returning(s_rows, a_rows):
        # get_sentiment_history runs the sentiment query first, then the ADP query.
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[FakeResult(s_rows), FakeResult(a_rows)])
        return db

    async def _test():
        from services import tracker_service

        s_rows = [
            {"t": datetime(2026, 8, 4, 12), "s": 0.5, "c": 4},
            {"t": datetime(2026, 8, 11, 12), "s": 0.1, "c": 6},
            {"t": datetime(2026, 8, 18, 12), "s": 0.3, "c": 5},
        ]
        a_rows = [
            {"t": datetime(2026, 8, 4, 12), "a": 10.0, "r": 5, "pr": 95.0},
            {"t": datetime(2026, 8, 11, 12), "a": 20.0, "r": 9, "pr": 90.0},
            {"t": datetime(2026, 8, 18, 12), "a": 6.0, "r": 3, "pr": 98.0},
        ]

        # [1] Merges sentiment + market (adp/rank/%rostered) into real per-metric points
        print("\n[1] Sentiment + ADP/rank/%rostered → per-metric points...")
        res = await tracker_service.get_sentiment_history("p1", "season", db_returning(s_rows, a_rows))
        assert res["count"] == 3
        p0 = res["points"][0]
        assert p0 == {"t": "2026-08-04", "sentiment": 0.5, "concern": 4.0, "adp": 10.0, "rank": 5.0, "rostered": 95.0}, p0
        assert "outlook" not in p0  # dropped the synthetic composite
        print(f"    PASS, {res['count']} pts, first={p0}")

        # [2] No market data → adp/rank/rostered null, sentiment/concern still present
        print("\n[2] No market data → adp/rank/rostered null...")
        res = await tracker_service.get_sentiment_history("p1", "season", db_returning(s_rows, []))
        assert all(p["adp"] is None and p["rank"] is None and p["rostered"] is None for p in res["points"])
        assert res["points"][0]["sentiment"] == 0.5
        print("    PASS, market null, sentiment intact")

        # [3] Unknown range falls back to season
        print("\n[3] Invalid range → season...")
        res = await tracker_service.get_sentiment_history("p1", "bogus", db_returning(s_rows, a_rows))
        assert res["range"] == "season", res["range"]
        print(f"    PASS, range={res['range']}")

        # [4] No history → empty points
        print("\n[4] Empty history → no points...")
        res = await tracker_service.get_sentiment_history("p1", "1w", db_returning([], []))
        assert res["count"] == 0 and res["points"] == []
        print(f"    PASS, {res}")

    asyncio.run(_test())
    print("\n✅ All sentiment history query tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5, Failure modes
# ══════════════════════════════════════════════════════════════════════════════

def run_failure_tests():
    print("\n" + "=" * 50)
    print("TRACKER, FAILURE MODE TESTS")
    print("=" * 50)

    async def _test():
        from services import tracker_service

        # [1] star_player, player not in DB → error, no exception
        print("\n[1] star_player for unknown player_id → error, no crash...")
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        async def mock_get_none(model, key):
            return None

        mock_db.get = mock_get_none
        result = await tracker_service.star_player(1, "bad_id", mock_db)
        assert result["status"] == "error", f"Expected error, got {result}"
        print(f"    PASS, {result}")

        # [2] get_tracked_players, DB failure → returns [], no crash
        print("\n[2] get_tracked_players with DB failure → empty list, no crash...")
        mock_db2 = AsyncMock()
        mock_db2.execute = AsyncMock(side_effect=Exception("DB connection lost"))
        result = await tracker_service.get_tracked_players(1, mock_db2)
        assert result == [], f"Expected [], got {result}"
        print(f"    PASS, empty list returned on DB failure")

        # [3] nflreadpy stats build, nflreadpy failure → context string fallback
        print("\n[3] build_stats_context with nflreadpy failure → fallback string...")
        from services.nflreadpy_service import build_stats_context
        with patch("services.nflreadpy_service.get_historical_stats",
                   new=AsyncMock(return_value={})), \
             patch("services.nflreadpy_service.get_recent_snap_share",
                   new=AsyncMock(return_value={})):
            ctx = await build_stats_context("Patrick Mahomes", "QB")
        assert ctx == "No historical stats available."
        print(f"    PASS, fallback context: '{ctx}'")

    asyncio.run(_test())
    print("\n✅ All failure mode tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_adp_trend_tests()
    run_star_unstar_tests()
    run_combined_score_tests()
    run_batch_analysis_tests()
    run_stock_serializer_tests()
    run_sentiment_snapshot_tests()
    run_sentiment_history_query_tests()
    run_router_tests()
    run_failure_tests()
    print("\n" + "=" * 50)
    print("ALL TRACKER TESTS PASSED ✅")
    print("=" * 50)
