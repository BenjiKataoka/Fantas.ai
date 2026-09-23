"""Tests for league_service's pure helpers.

Usage: python3 tests/test_league_service.py

gather_per_league replaced two hand-written copies of the same fan-out. The happy
path is covered by /matchups and /results returning real data; what needs pinning is
the failure behaviour, because one league going down must not take the others with it.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.espn_service import EspnAuthError
from services.league_service import gather_per_league

LEAGUES = [
    {"platform": "SLEEPER", "league_id": "s1"},
    {"platform": "ESPN", "league_id": "e1"},
    {"platform": "SLEEPER", "league_id": "s2"},
]


def run_gather_tests():
    print("\n" + "=" * 50)
    print("LEAGUE SERVICE, gather_per_league()")
    print("=" * 50)

    async def ok_sleeper(l): return f"sleeper:{l['league_id']}"
    async def ok_espn(l): return f"espn:{l['league_id']}"

    out = asyncio.run(gather_per_league(LEAGUES, sleeper=ok_sleeper, espn=ok_espn, tag="Test"))
    assert out == ["sleeper:s1", "espn:e1", "sleeper:s2"], out
    print("    PASS, results come back in league order, dispatched by platform")

    # Expired ESPN cookies are a distinct outcome, not a failure: callers show a
    # reconnect warning for that league and render the rest.
    async def expired_espn(l): raise EspnAuthError("cookies rejected")
    out = asyncio.run(gather_per_league(LEAGUES, sleeper=ok_sleeper, espn=expired_espn, tag="Test"))
    assert out == ["sleeper:s1", "expired", "sleeper:s2"], out
    print("    PASS, EspnAuthError becomes 'expired' and the Sleeper leagues still load")

    async def boom(l): raise RuntimeError("upstream is down")
    out = asyncio.run(gather_per_league(LEAGUES, sleeper=ok_sleeper, espn=boom, tag="Test"))
    assert out == ["sleeper:s1", None, "sleeper:s2"], out
    print("    PASS, an unexpected error becomes None without cancelling the others")

    out = asyncio.run(gather_per_league(LEAGUES, sleeper=boom, espn=boom, tag="Test"))
    assert out == [None, None, None], out
    assert len(out) == len(LEAGUES), "length must always match so callers can zip"
    print("    PASS, every league failing still returns one slot per league")

    assert asyncio.run(gather_per_league([], sleeper=boom, espn=boom, tag="Test")) == []
    print("    PASS, no leagues returns an empty list")

    print("\n✅ gather_per_league tests passed.")


if __name__ == "__main__":
    run_gather_tests()
