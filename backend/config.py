import os
from dotenv import load_dotenv, find_dotenv

# find_dotenv() walks up from this file's location to find .env — works regardless of CWD
load_dotenv(find_dotenv())

DATABASE_URL: str = os.environ["DATABASE_URL"]
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]

ESPN_LEAGUE_ID: int | None = int(os.environ["ESPN_LEAGUE_ID"]) if os.environ.get("ESPN_LEAGUE_ID") else None
ESPN_S2: str | None = os.environ.get("ESPN_S2")
SWID: str | None = os.environ.get("SWID")
SLEEPER_USERNAME: str | None = os.environ.get("SLEEPER_USERNAME")

# Projection source weights (user-adjustable via /api/settings)
DEFAULT_WEIGHTS = {
    "sleeper": 0.35,
    "espn": 0.30,
    "fp": 0.35,
}

# Gemini models (upgraded Sep 2026 from the 2.0 family)
# Free tier is Flash-class only — Pro moved behind billing May 2026.
# gemini-3.1-flash-lite: stable, cheap/high-volume primary — used for the cheap
#   passes (news Pass 1, context regen; tracker Pass 1 + Pass 4).
# gemini-3.7-flash:      stable, more capable fallback — used for the harder passes
#   (news Pass 2 contradiction detection; tracker Pass 2 + Pass 3).
# Override via env if Google shifts the current free Flash IDs (check AI Studio).
GEMINI_PRIMARY = os.environ.get("GEMINI_PRIMARY", "gemini-3.1-flash-lite")
GEMINI_FALLBACK = os.environ.get("GEMINI_FALLBACK", "gemini-3.7-flash")

# Max Gemini calls per 30-minute window
GEMINI_CALLS_PER_WINDOW = 10

# Global kill switch for all LLM/Gemini API calls. Set LLM_ENABLED=false in .env to
# halt every Gemini call (news + tracker) without touching the network — pipelines
# fall back to rule-based signals. Useful for testing the rest of the app for free.
LLM_ENABLED: bool = os.environ.get("LLM_ENABLED", "true").strip().lower() not in ("false", "0", "no")

# Hard daily ceiling on Gemini calls (protects the free-tier key). Once hit, the app
# stops calling Gemini for the rest of the UTC day and degrades to rule-based signals.
# Free tier is ~1,500 requests/day; default leaves headroom.
LLM_DAILY_CALL_CAP: int = int(os.environ.get("LLM_DAILY_CALL_CAP", "1200"))

# ── Clerk auth ─────────────────────────────────────────────────────────────────
# When CLERK_SECRET_KEY is unset, the backend runs in DEV-FALLBACK mode: all requests
# resolve to a single local dev user (no real auth). Setting the keys switches on real
# JWT verification + the per-user approval gate. Get these from Clerk → API Keys.
CLERK_PUBLISHABLE_KEY: str | None = os.environ.get("CLERK_PUBLISHABLE_KEY")
CLERK_SECRET_KEY: str | None = os.environ.get("CLERK_SECRET_KEY")
# Optional explicit override; otherwise derived from the publishable key at runtime.
CLERK_JWT_ISSUER: str | None = os.environ.get("CLERK_JWT_ISSUER")
# Comma-separated Clerk user IDs that are auto-approved + treated as admins (you).
CLERK_ADMIN_IDS: set[str] = {
    s.strip() for s in os.environ.get("CLERK_ADMIN_IDS", "").split(",") if s.strip()
}

AUTH_ENABLED: bool = bool(CLERK_SECRET_KEY)
