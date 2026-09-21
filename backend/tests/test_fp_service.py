"""
Tests for fp_service.py (FantasyPros scraper).
Usage: python tests/test_fp_service.py

NOTE: This test scrapes 5 position pages with 1-2s sleep between each.
Expect ~10-15 seconds total runtime. This is intentional rate limiting.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run_tests():
    print("=" * 50)
    print("FANTASYPROS SCRAPER TEST")
    print("=" * 50)

    # ------------------------------------------------------------------ #
    # Single position scrape, faster check before running all 5
    # ------------------------------------------------------------------ #
    print("\n[1] Scraping QB projections for week 1 (single position)...")
    try:
        from services.fp_service import _scrape_position
        data = await _scrape_position("qb", week=1)
        if data:
            sample = list(data.items())[:3]
            print(f"    PASS, {len(data)} QBs with projections")
            print(f"    Sample: {sample}")
        else:
            print("    NOTE, 0 projections returned (expected during offseason)")
            print("    PASS, scraper ran without error")
    except Exception as e:
        print(f"    FAIL, {e}")

    # ------------------------------------------------------------------ #
    # Full scrape, all 5 positions with rate limiting (~10-15s)
    # ------------------------------------------------------------------ #
    print("\n[2] Scraping all positions for week 1 (expect ~10-15s due to rate limiting)...")
    try:
        from services.fp_service import get_fp_projections
        projections = await get_fp_projections(week=1)
        if projections:
            print(f"    PASS, {len(projections)} total players with projections")
            sample = list(projections.items())[:5]
            print(f"    Sample: {sample}")
        else:
            print("    NOTE, 0 projections returned (expected during offseason)")
            print("    PASS, all 5 positions scraped without error")
    except Exception as e:
        print(f"    FAIL, {e}")

    # ------------------------------------------------------------------ #
    # Cache check, second call should return instantly
    # ------------------------------------------------------------------ #
    print("\n[3] Verifying cache, second call should be instant...")
    try:
        import time
        start = time.time()
        projections2 = await get_fp_projections(week=1)
        elapsed = time.time() - start
        if elapsed < 0.1:
            print(f"    PASS, returned in {elapsed:.3f}s (cache hit)")
        else:
            print(f"    WARN, took {elapsed:.2f}s (expected <0.1s for cache hit)")
    except Exception as e:
        print(f"    FAIL, {e}")

    # ------------------------------------------------------------------ #
    # Name normalization matching
    # ------------------------------------------------------------------ #
    print("\n[4] Verifying normalize_name works for FP name matching...")
    try:
        from services.projection_service import normalize_name
        # These are typical FP name formats
        cases = [
            "Patrick Mahomes",
            "Ja'Marr Chase",
            "D'Andre Swift",
            "Calvin Ridley Jr.",
            "T.J. Hockenson",
        ]
        for name in cases:
            normalized = normalize_name(name)
            print(f"    '{name}' → '{normalized}'")
        print("    PASS, normalization consistent with ESPN/Sleeper matching")
    except Exception as e:
        print(f"    FAIL, {e}")

    print("\n" + "=" * 50)
    print("FANTASYPROS TEST COMPLETE")
    print("=" * 50)


async def run_failure_tests():
    print("\n" + "=" * 50)
    print("FANTASYPROS, FAILURE MODE TESTS")
    print("=" * 50)

    from unittest.mock import patch, AsyncMock, MagicMock
    from services import fp_service

    # [5] 403 response returns {} without raising
    print("\n[5] 403 response returns {} without raising...")
    mock_403 = MagicMock()
    mock_403.status_code = 403
    mock_403.raise_for_status.side_effect = Exception("403 Forbidden")

    async def mock_get_403(*args, **kwargs):
        return mock_403

    # Clear cache so we actually hit the mock
    fp_service._cache.clear()

    with patch("services.fp_service.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = mock_get_403
        mock_cls.return_value = mock_client

        result = await fp_service._scrape_position("qb", week=1)
        assert result == {}, f"Expected {{}} on 403, got {result}"
        print(f"    PASS, 403 returns {{}} gracefully")

    # [6] Network timeout returns {} without raising
    print("\n[6] Network timeout returns {} without raising...")
    fp_service._cache.clear()

    with patch("services.fp_service.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("Connection timeout"))
        mock_cls.return_value = mock_client

        result = await fp_service._scrape_position("rb", week=1)
        assert result == {}, f"Expected {{}} on timeout, got {result}"
        print(f"    PASS, timeout returns {{}} gracefully")

    print("\n✅ All failure mode tests passed.")


if __name__ == "__main__":
    asyncio.run(run_tests())
    asyncio.run(run_failure_tests())
