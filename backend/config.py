import os
from dotenv import load_dotenv

load_dotenv()

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
GEMINI_PRIMARY = "gemini-2.5-flash-lite"
GEMINI_FALLBACK = "gemini-2.5-flash"

# Max Gemini calls per 30-minute window
GEMINI_CALLS_PER_WINDOW = 10
