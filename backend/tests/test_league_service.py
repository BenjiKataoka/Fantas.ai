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

from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from services.espn_service import EspnAuthError
from services.league_service import gather_per_league, resolve_sleeper_user_id

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


def run_sleeper_pin_tests():
    """sleeper_username comes from the query string, so it must be pinned to the account
    this login already connected. Untrusted, one request naming someone else rebound the
    caller's stored Sleeper identity and synced a stranger's roster into their dashboard."""
    print("\n" + "=" * 50)
    print("SLEEPER ACCOUNT PINNING")
    print("=" * 50)

    class U:
        def __init__(self, uid): self.sleeper_user_id = uid

    def resolve(user, username, lookup="stranger99"):
        with patch("services.sleeper_service.get_user_id", AsyncMock(return_value=lookup)):
            return asyncio.run(resolve_sleeper_user_id(user, username))

    # No username: the saved account, which is how every page works after connecting.
    assert resolve(U("mine123"), None) == "mine123"
    print("    PASS, no username falls back to the connected account")

    # First connection: nothing saved yet, so this is what does the binding.
    assert resolve(U(None), "newuser", lookup="fresh456") == "fresh456"
    print("    PASS, the first connection can still bind an account")

    # Your own username, spelled out. The common case, must not 403.
    assert resolve(U("mine123"), "myname", lookup="mine123") == "mine123"
    print("    PASS, naming your own connected account is allowed")

    # Someone else's. This is the hole.
    try:
        resolve(U("mine123"), "someone_else", lookup="stranger99")
        raise AssertionError("a stranger's username was accepted")
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
    print("    PASS, a stranger's username is refused with 403")

    # An unresolvable username must not read as "no mismatch" and slip through.
    assert resolve(U("mine123"), "ghost", lookup=None) is None
    print("    PASS, an unknown username resolves to None rather than the saved account")

    print("\n✅ Sleeper pinning tests passed.")


if __name__ == "__main__":
    run_gather_tests()
    run_sleeper_pin_tests()
