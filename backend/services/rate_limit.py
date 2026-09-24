"""
Per-user request limits, keyed on the VERIFIED Clerk id.

Checked inside auth.get_current_user after the JWT is verified. A middleware would run
before verification, so it could only key on an unverified claim, and anyone could then
spend another user's budget by sending junk tokens carrying their id.

ponytail: in-memory and per-process. One uvicorn worker is the deploy target; with N
workers each keeps its own counters, so the effective limit is N times higher. Move the
counters to Redis only if that ever matters.
"""
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException

WINDOW = 60.0

# ~4x the busiest real session measured (39 API calls in 18s of back-to-back page reloads,
# half of them React's dev-only double effects), so normal use never meets it.
DEFAULT_LIMIT = 240

# These fan out to Sleeper/ESPN once per league or start Gemini work. A flood here costs
# real upstream calls and risks the server's IP being throttled, not just our CPU.
EXPENSIVE_PREFIXES = (
    "/api/portfolio", "/api/matchups", "/api/waivers", "/api/results", "/api/recap",
    "/api/roster", "/api/startsit", "/api/tape",
    "/api/tracker/refresh", "/api/tracker/analyze-roster", "/api/tracker/star",
)
EXPENSIVE_LIMIT = 60

_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def check(key: str, path: str, now: Optional[float] = None) -> None:
    """Record one request for `key`, or raise 429 with Retry-After once over the limit."""
    expensive = path.startswith(EXPENSIVE_PREFIXES)
    limit = EXPENSIVE_LIMIT if expensive else DEFAULT_LIMIT
    now = time.monotonic() if now is None else now
    hits = _hits[(key, "expensive" if expensive else "default")]
    while hits and hits[0] <= now - WINDOW:
        hits.popleft()
    if len(hits) >= limit:
        retry_after = max(1, int(hits[0] + WINDOW - now) + 1)
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Give it a moment and try again.",
            headers={"Retry-After": str(retry_after)},
        )
    hits.append(now)


def reset() -> None:
    """Forget every counter. For tests."""
    _hits.clear()
