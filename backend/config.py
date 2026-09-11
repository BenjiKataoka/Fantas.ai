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

# Gemini models
# gemini-2.0-flash-lite: 1,500 RPD free tier (vs 20 for 2.5-flash-lite preview)
# gemini-2.0-flash:      1,500 RPD free tier fallback
GEMINI_PRIMARY = "gemini-2.0-flash-lite"
GEMINI_FALLBACK = "gemini-2.0-flash"

# Max Gemini calls per 30-minute window
GEMINI_CALLS_PER_WINDOW = 10
