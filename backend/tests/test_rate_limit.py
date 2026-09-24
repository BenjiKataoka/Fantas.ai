"""
Rate limiter: the thresholds, the window sliding, and the tier split.

Run: venv/bin/python tests/test_rate_limit.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException

from services import rate_limit as rl


def blocked(key, path, now):
    try:
        rl.check(key, path, now)
        return None
    except HTTPException as e:
        assert e.status_code == 429, e.status_code
        return int(e.headers["Retry-After"])


def test_default_tier():
    rl.reset()
    for i in range(rl.DEFAULT_LIMIT):
        assert blocked("u1", "/api/settings", 0.0 + i * 0.01) is None, f"blocked early at {i}"
    retry = blocked("u1", "/api/settings", 5.0)
    assert retry is not None, "the request past the limit went through"
    assert 1 <= retry <= rl.WINDOW + 1, retry
    print(f"  PASS, {rl.DEFAULT_LIMIT} allowed, the next refused with Retry-After {retry}s")


def test_window_slides():
    rl.reset()
    for i in range(rl.DEFAULT_LIMIT):
        rl.check("u1", "/api/settings", float(i) * 0.1)
    assert blocked("u1", "/api/settings", 10.0) is not None
    # Once the oldest hits age out of the 60s window, requests flow again.
    assert blocked("u1", "/api/settings", rl.WINDOW + 1.0) is None
    print("  PASS, requests flow again once old ones leave the window")


def test_users_are_independent():
    rl.reset()
    for i in range(rl.DEFAULT_LIMIT):
        rl.check("u1", "/api/settings", 0.0)
    assert blocked("u1", "/api/settings", 1.0) is not None
    assert blocked("u2", "/api/settings", 1.0) is None, "one user's flood blocked another"
    print("  PASS, one user hitting the limit never blocks another")


def test_expensive_tier_is_tighter_and_separate():
    rl.reset()
    for i in range(rl.EXPENSIVE_LIMIT):
        assert blocked("u1", "/api/portfolio", 0.0) is None
    assert blocked("u1", "/api/portfolio", 1.0) is not None, "expensive limit not enforced"
    assert blocked("u1", "/api/waivers", 1.0) is not None, "expensive endpoints share one budget"
    # Cheap pages keep working while the fan-out budget is spent.
    assert blocked("u1", "/api/settings", 1.0) is None, "expensive flood blocked cheap reads"
    # Prefix match covers path parameters.
    assert rl.check("u2", "/api/tracker/star/4046", 0.0) is None
    print(f"  PASS, fan-out endpoints capped at {rl.EXPENSIVE_LIMIT}/min without blocking the rest")


if __name__ == "__main__":
    for t in (test_default_tier, test_window_slides, test_users_are_independent,
              test_expensive_tier_is_tighter_and_separate):
        print(t.__name__)
        t()
    print("\nAll rate limit tests passed.")
