"""
Tests for Phase 4.6 — Player Tracker.
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
# SECTION 1 — ADP trend calculation
# ══════════════════════════════════════════════════════════════════════════════

def run_adp_trend_tests():
    print("=" * 50)
    print("TRACKER — ADP TREND TESTS")
    print("=" * 50)

    async def _test():
        from services.adp_service import compute_adp_trend

        mock_db = AsyncMock()
        now = datetime.utcnow()

        # [1] RISING — ADP improved by > 2 positions (lower number = better)
        print("\n[1] RISING trend — ADP moved from 30 to 25...")
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
        print(f"    PASS — trend=RISING, delta={result['delta']}")

        # [2] FALLING — ADP worsened by > 2 positions
        print("\n[2] FALLING trend — ADP moved from 20 to 26...")
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
        print(f"    PASS — trend=FALLING, delta={result['delta']}")

        # [3] STABLE — within ±2 positions
        print("\n[3] STABLE trend — ADP within 2 positions...")
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
        print(f"    PASS — trend=STABLE, delta={result['delta']}")

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
        print(f"    PASS — empty data returns STABLE gracefully")

    asyncio.run(_test())
    print("\n✅ All ADP trend tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Star / Unstar
# ══════════════════════════════════════════════════════════════════════════════

def run_star_unstar_tests():
    print("\n" + "=" * 50)
    print("TRACKER — STAR / UNSTAR TESTS")
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
        print(f"    PASS — {result}")

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
        print(f"    PASS — {result}")

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
        print(f"    PASS — {result}")

        # [4] Unstar player not in tracker
        print("\n[4] Unstar player not in tracker → 'not_found'...")
        async def mock_get_none(model, key):
            return None

        mock_db.get = mock_get_none
        result = await tracker_service.unstar_player(1, "nobody", mock_db)
        assert result["status"] == "not_found"
        print(f"    PASS — {result}")

    asyncio.run(_test())
    print("\n✅ All star/unstar tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Combined score formula
# ══════════════════════════════════════════════════════════════════════════════

def run_combined_score_tests():
    print("\n" + "=" * 50)
    print("TRACKER — COMBINED SCORE FORMULA TESTS")
    print("=" * 50)

    from services.sentiment_service import ADP_PENALTY

    # Formula: (concern_level × 0.50) + (worry_score × 0.30) + (adp_penalty × 0.20)
    # [1] Worst case: concern=10, worry=10, FALLING (+2)
    print("\n[1] Worst-case: concern=10, worry=10, FALLING...")
    score = (10 * 0.50) + (10 * 0.30) + (ADP_PENALTY["FALLING"] * 0.20)
    assert score == 8.4, f"Expected 8.4, got {score}"
    print(f"    PASS — combined_score={score}")

    # [2] Best case: concern=1, worry=1, RISING (-1)
    print("\n[2] Best-case: concern=1, worry=1, RISING...")
    score = round((1 * 0.50) + (1 * 0.30) + (ADP_PENALTY["RISING"] * 0.20), 2)
    assert score == 0.6, f"Expected 0.6, got {score}"
    print(f"    PASS — combined_score={score}")

    # [3] Neutral: concern=5, worry=5, STABLE
    print("\n[3] Neutral: concern=5, worry=5, STABLE...")
    score = (5 * 0.50) + (5 * 0.30) + (ADP_PENALTY["STABLE"] * 0.20)
    assert score == 4.0, f"Expected 4.0, got {score}"
    print(f"    PASS — combined_score={score}")

    print("\n✅ All combined score tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Router endpoints
# ══════════════════════════════════════════════════════════════════════════════

def run_router_tests():
    print("\n" + "=" * 50)
    print("TRACKER — ROUTER TESTS")
    print("=" * 50)

    from fastapi.testclient import TestClient
    from main import app
    from auth import get_current_user

    # Fixed authenticated user so auth doesn't consult the (unmocked) DB in these tests.
    fake_user = MagicMock(id=1, is_approved=True, clerk_id="test")
    app.dependency_overrides[get_current_user] = lambda: fake_user

    with TestClient(app) as client:

        # [1] GET /api/tracker — returns list (empty is fine)
        print("\n[1] GET /api/tracker returns 200...")
        with patch("routers.tracker.tracker_service.get_tracked_players",
                   new=AsyncMock(return_value=[])):
            resp = client.get("/api/tracker")
        assert resp.status_code == 200
        data = resp.json()
        assert "tracked_players" in data
        assert "total" in data
        print(f"    PASS — status=200, total={data['total']}")

        # [2] GET /api/tracker/{player_id} — not found returns 404
        print("\n[2] GET /api/tracker/unknown returns 404...")
        with patch("routers.tracker.tracker_service.get_tracked_player_detail",
                   new=AsyncMock(return_value=None)):
            resp = client.get("/api/tracker/unknown_player_id")
        assert resp.status_code == 404
        print(f"    PASS — 404 for untracked player")

        # [3] POST /api/tracker/star/{player_id} — success
        print("\n[3] POST /api/tracker/star/test_player_id returns 200...")
        with patch("routers.tracker.tracker_service.star_player",
                   new=AsyncMock(return_value={"status": "starred", "player_id": "test_id"})):
            resp = client.post("/api/tracker/star/test_player_id")
        assert resp.status_code == 200
        assert resp.json()["status"] == "starred"
        print(f"    PASS — star returned {resp.json()}")

        # [4] DELETE /api/tracker/star/{player_id} — not found returns 404
        print("\n[4] DELETE /api/tracker/star/unknown returns 404...")
        with patch("routers.tracker.tracker_service.unstar_player",
                   new=AsyncMock(return_value={"status": "not_found"})):
            resp = client.delete("/api/tracker/star/unknown")
        assert resp.status_code == 404
        print(f"    PASS — 404 for unstarred player")

        # [5] POST /api/tracker/refresh/{player_id} — success
        print("\n[5] POST /api/tracker/refresh/test_id returns 200...")
        with patch("routers.tracker.tracker_service.refresh_profile",
                   new=AsyncMock(return_value=True)):
            resp = client.post("/api/tracker/refresh/test_player_id")
        assert resp.status_code == 200
        assert resp.json()["status"] == "refresh_triggered"
        print(f"    PASS — refresh returned {resp.json()}")

        # [6] POST /api/tracker/analyze-roster — kicks off batch, returns counts
        print("\n[6] POST /api/tracker/analyze-roster returns queued counts...")
        with patch("routers.tracker.tracker_service.analyze_roster",
                   new=AsyncMock(return_value={"status": "started", "queued": 12,
                                               "skipped_fresh": 3, "total": 15})):
            resp = client.post("/api/tracker/analyze-roster")
        assert resp.status_code == 200
        body = resp.json()
        assert body["queued"] == 12 and body["total"] == 15
        print(f"    PASS — analyze-roster returned {body}")

        # [7] GET /api/tracker/roster-analysis — static path not shadowed by {player_id}
        print("\n[7] GET /api/tracker/roster-analysis returns progress...")
        with patch("routers.tracker.tracker_service.roster_analysis_status",
                   new=AsyncMock(return_value={"total": 15, "ready": 9, "pending": 6})):
            resp = client.get("/api/tracker/roster-analysis")
        assert resp.status_code == 200, f"static route shadowed? got {resp.status_code}"
        assert resp.json()["ready"] == 9
        print(f"    PASS — roster-analysis returned {resp.json()}")

    app.dependency_overrides.clear()
    print("\n✅ All router tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4.5 — Batch roster analysis (freshness skip + queueing)
# ══════════════════════════════════════════════════════════════════════════════

def run_batch_analysis_tests():
    print("\n" + "=" * 50)
    print("TRACKER — BATCH ROSTER ANALYSIS")
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

        with patch("services.tracker_service.get_nfl_state",
                   new=AsyncMock(return_value={"season_type": "regular"})), \
             patch("services.tracker_service._analyze_roster_worker", new=fake_worker):
            result = await tracker_service.analyze_roster(1, mock_db)
            await asyncio.sleep(0)  # let the fire-and-forget worker task run

        assert result == {"status": "started", "queued": 2, "skipped_fresh": 1, "total": 3}, result
        assert set(captured["ids"]) == {"p2", "p3"}, captured
        print(f"    PASS — {result}, queued ids={sorted(captured['ids'])}")

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
        print(f"    PASS — {result}")

        # [3] force=True re-queues even fresh players
        print("\n[3] force=True → all players queued despite fresh profiles...")
        mock_db3 = AsyncMock()
        mock_db3.execute = AsyncMock(return_value=roster_of("p1", "p2"))
        mock_db3.get = get_fresh
        cap3 = {}
        async def worker3(user_id, player_ids):
            cap3["ids"] = player_ids
        with patch("services.tracker_service.get_nfl_state",
                   new=AsyncMock(return_value={"season_type": "regular"})), \
             patch("services.tracker_service._analyze_roster_worker", new=worker3):
            result = await tracker_service.analyze_roster(1, mock_db3, force=True)
            await asyncio.sleep(0)
        assert result["queued"] == 2 and result["skipped_fresh"] == 0, result
        print(f"    PASS — {result}")

        # [4] Empty roster → empty status, no crash
        print("\n[4] Empty roster → status=empty...")
        mock_db4 = AsyncMock()
        mock_db4.execute = AsyncMock(return_value=roster_of())
        result = await tracker_service.analyze_roster(1, mock_db4)
        assert result == {"status": "empty", "queued": 0, "skipped_fresh": 0, "total": 0}, result
        print(f"    PASS — {result}")

    asyncio.run(_test())
    print("\n✅ All batch analysis tests passed.")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Failure modes
# ══════════════════════════════════════════════════════════════════════════════

def run_failure_tests():
    print("\n" + "=" * 50)
    print("TRACKER — FAILURE MODE TESTS")
    print("=" * 50)

    async def _test():
        from services import tracker_service

        # [1] star_player — player not in DB → error, no exception
        print("\n[1] star_player for unknown player_id → error, no crash...")
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        async def mock_get_none(model, key):
            return None

        mock_db.get = mock_get_none
        result = await tracker_service.star_player(1, "bad_id", mock_db)
        assert result["status"] == "error", f"Expected error, got {result}"
        print(f"    PASS — {result}")

        # [2] get_tracked_players — DB failure → returns [], no crash
        print("\n[2] get_tracked_players with DB failure → empty list, no crash...")
        mock_db2 = AsyncMock()
        mock_db2.execute = AsyncMock(side_effect=Exception("DB connection lost"))
        result = await tracker_service.get_tracked_players(1, mock_db2)
        assert result == [], f"Expected [], got {result}"
        print(f"    PASS — empty list returned on DB failure")

        # [3] nflreadpy stats build — nflreadpy failure → context string fallback
        print("\n[3] build_stats_context with nflreadpy failure → fallback string...")
        from services.nflreadpy_service import build_stats_context
        with patch("services.nflreadpy_service.get_historical_stats",
                   new=AsyncMock(return_value={})), \
             patch("services.nflreadpy_service.get_recent_snap_share",
                   new=AsyncMock(return_value={})):
            ctx = await build_stats_context("Patrick Mahomes", "QB")
        assert ctx == "No historical stats available."
        print(f"    PASS — fallback context: '{ctx}'")

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
    run_router_tests()
    run_failure_tests()
    print("\n" + "=" * 50)
    print("ALL TRACKER TESTS PASSED ✅")
    print("=" * 50)
