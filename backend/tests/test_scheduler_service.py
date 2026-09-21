"""
Tests for the background scheduler (Phase 5).
Covers: trackable-player collection, the ADP refresh job (success + per-player failure
isolation), and start/shutdown gating. Job logic is tested directly, not cron timing.
Usage: python3 tests/test_scheduler_service.py
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import AsyncMock, MagicMock, patch


class FakeResult:
    def __init__(self, rows): self._rows = rows
    def mappings(self): return self
    def all(self): return self._rows


class FakeSession:
    """Async-context-manager stand-in for AsyncSessionLocal()."""
    def __init__(self, db): self._db = db
    async def __aenter__(self): return self._db
    async def __aexit__(self, *a): return False


def run_trackable_tests():
    print("=" * 50)
    print("SCHEDULER, TRACKABLE PLAYERS")
    print("=" * 50)

    async def _test():
        from services import tracker_service
        db = AsyncMock()
        db.execute = AsyncMock(return_value=FakeResult([
            {"player_id": "p1", "name": "Alice"},
            {"player_id": "p2", "name": "Bob"},
        ]))
        res = await tracker_service.get_trackable_players(db)
        assert res == [("p1", "Alice"), ("p2", "Bob")], res
        print(f"    PASS, {res}")

    asyncio.run(_test())
    print("✅ trackable players ok")


def run_market_job_tests():
    print("\n" + "=" * 50)
    print("SCHEDULER, MARKET REFRESH JOB (ESPN rank + %rostered)")
    print("=" * 50)

    pool = {
        "alice": {"espn_id": "1", "position": "RB", "position_rank": 3, "overall_rank": 5, "adp": 8.7, "percent_rostered": 99.9},
        "bob":   {"espn_id": "2", "position": "WR", "position_rank": 7, "overall_rank": 37, "adp": 28.9, "percent_rostered": 96.0},
    }

    async def _test():
        from services import scheduler_service

        # [1] Stores an ESPN row per matched tracked player; unmatched are counted as missed
        print("\n[1] Matches tracked players against the ESPN pool...")
        mock_db = AsyncMock(); mock_db.add = MagicMock(); mock_db.commit = AsyncMock()
        with patch("database.AsyncSessionLocal", return_value=FakeSession(mock_db)), \
             patch("services.projection_service.get_nfl_state",
                   new=AsyncMock(return_value={"season": 2026, "week": 2})), \
             patch("services.espn_service.get_espn_market_pool", new=AsyncMock(return_value=pool)), \
             patch("services.tracker_service.get_trackable_players",
                   new=AsyncMock(return_value=[("p1", "Alice"), ("p2", "Bob"), ("p3", "Nobody Here")])):
            res = await scheduler_service.refresh_market_job()
        assert res == {"players": 3, "matched": 2, "missed": 1, "pool": 2}, res
        assert mock_db.add.call_count == 2
        assert mock_db.commit.await_count == 1
        # verify a stored row carries rank + %rostered
        row = mock_db.add.call_args_list[0][0][0]
        assert row.source == "ESPN" and row.position_rank == 3 and row.percent_rostered == 99.9
        print(f"    PASS, {res}, first row RB{row.position_rank}, {row.percent_rostered}% rostered")

        # [2] Empty pool (ESPN down) → no-op, no crash
        print("\n[2] Empty ESPN pool → skip cleanly...")
        with patch("services.projection_service.get_nfl_state",
                   new=AsyncMock(return_value={"season": 2026, "week": 2})), \
             patch("services.espn_service.get_espn_market_pool", new=AsyncMock(return_value={})):
            res = await scheduler_service.refresh_market_job()
        assert res == {"players": 0, "matched": 0, "missed": 0, "pool": 0}, res
        print(f"    PASS, {res}")

    asyncio.run(_test())
    print("✅ market job ok")


def run_sentiment_job_tests():
    print("\n" + "=" * 50)
    print("SCHEDULER, SENTIMENT REFRESH JOB (stale-only + budget gate)")
    print("=" * 50)

    async def _test():
        from services import scheduler_service

        # [1] Analyzes only the stale players, paced; fresh ones are skipped
        print("\n[1] Runs stale players only, skips fresh...")
        stale = [("p1", "Alice"), ("p2", "Bob")]
        analyzed = []

        async def fake_analyze(uid, pid):
            analyzed.append(pid)
            return True

        big_budget = {"remaining": 1000, "by_model": {"gemini-3.1-flash-lite": {"remaining": 1000}}}
        with patch("services.tracker_service.get_stale_trackable_players",
                   new=AsyncMock(return_value=(stale, 3))), \
             patch("services.tracker_service.analyze_one_player", new=AsyncMock(side_effect=fake_analyze)), \
             patch("services.scheduler_service._representative_user_id", new=AsyncMock(return_value=7)), \
             patch("services.llm_budget.usage", return_value=big_budget), \
             patch("services.tracker_service.ROSTER_PACE_SECONDS", 0), \
             patch("config.GEMINI_PRIMARY", "gemini-3.1-flash-lite"):
            scheduler_service._sentiment_running = False
            res = await scheduler_service.refresh_sentiment_job()
        assert res == {"stale": 2, "analyzed": 2, "skipped_fresh": 3, "failed": 0, "budget_stopped": False}, res
        assert analyzed == ["p1", "p2"], analyzed
        print(f"    PASS, {res}")

        # [2] Budget below a full player's passes → stops before spending, none analyzed
        print("\n[2] Budget headroom below 4 passes → halts cleanly...")
        low_budget = {"remaining": 2, "by_model": {"gemini-3.1-flash-lite": {"remaining": 2}}}
        with patch("services.tracker_service.get_stale_trackable_players",
                   new=AsyncMock(return_value=(stale, 0))), \
             patch("services.tracker_service.analyze_one_player", new=AsyncMock(return_value=True)) as spy, \
             patch("services.scheduler_service._representative_user_id", new=AsyncMock(return_value=7)), \
             patch("services.llm_budget.usage", return_value=low_budget), \
             patch("services.tracker_service.ROSTER_PACE_SECONDS", 0), \
             patch("config.GEMINI_PRIMARY", "gemini-3.1-flash-lite"):
            scheduler_service._sentiment_running = False
            res = await scheduler_service.refresh_sentiment_job()
        assert res["budget_stopped"] is True and res["analyzed"] == 0, res
        assert spy.await_count == 0, spy.await_count
        print(f"    PASS, {res}")

        # [3] Overlap guard rejects a concurrent run
        print("\n[3] Already-running guard...")
        scheduler_service._sentiment_running = True
        try:
            res = await scheduler_service.refresh_sentiment_job()
            assert res == {"status": "already_running"}, res
        finally:
            scheduler_service._sentiment_running = False
        print(f"    PASS, {res}")

    asyncio.run(_test())
    print("✅ sentiment job ok")


def run_lifecycle_tests():
    print("\n" + "=" * 50)
    print("SCHEDULER, START/SHUTDOWN GATING")
    print("=" * 50)
    from services import scheduler_service

    # [1] Disabled (default) → start is a no-op, no scheduler created
    print("\n[1] SCHEDULER_ENABLED=false → no-op...")
    scheduler_service.shutdown_scheduler()
    with patch("services.scheduler_service.SCHEDULER_ENABLED", False):
        scheduler_service.start_scheduler()
    assert scheduler_service._scheduler is None
    print("    PASS, nothing started when disabled")

    # [2] Enabled → creates scheduler, registers both jobs, starts; shutdown clears it
    print("\n[2] SCHEDULER_ENABLED=true → wires both jobs...")
    with patch("services.scheduler_service.SCHEDULER_ENABLED", True), \
         patch("services.scheduler_service.AsyncIOScheduler") as MockSched:
        inst = MockSched.return_value
        scheduler_service._scheduler = None
        scheduler_service.start_scheduler()
        assert MockSched.called
        assert inst.add_job.call_count == 2, inst.add_job.call_count
        assert inst.start.called
        scheduler_service.shutdown_scheduler()
        assert inst.shutdown.called
        assert scheduler_service._scheduler is None
    print("    PASS, 2 jobs registered, start+shutdown called")


if __name__ == "__main__":
    run_trackable_tests()
    run_market_job_tests()
    run_sentiment_job_tests()
    run_lifecycle_tests()
    print("\n" + "=" * 50)
    print("ALL SCHEDULER TESTS PASSED ✅")
    print("=" * 50)
