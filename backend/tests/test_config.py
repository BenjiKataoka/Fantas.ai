"""
Verify all required environment variables load correctly from .env
Usage: python test_config.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_tests():
    print("=" * 50)
    print("CONFIG TEST")
    print("=" * 50)

    try:
        from config import (
            DATABASE_URL,
            GEMINI_API_KEY,
            DEFAULT_WEIGHTS,
            GEMINI_PRIMARY,
            GEMINI_FALLBACK,
            GEMINI_CALLS_PER_WINDOW,
        )
        print("\n[1] Config imported successfully")
    except Exception as e:
        print(f"\n[1] FAIL — could not import config: {e}")
        return

    # DATABASE_URL
    if DATABASE_URL and DATABASE_URL.startswith("postgresql+asyncpg://"):
        print("[2] PASS — DATABASE_URL present and uses asyncpg driver")
    else:
        print(f"[2] FAIL — DATABASE_URL missing or wrong format: {DATABASE_URL!r}")

    # GEMINI_API_KEY
    if GEMINI_API_KEY and len(GEMINI_API_KEY) > 10:
        print("[3] PASS — GEMINI_API_KEY present")
    else:
        print("[3] FAIL — GEMINI_API_KEY missing or too short")

    # Optional credentials — warn but don't fail
    from config import ESPN_LEAGUE_ID, ESPN_S2, SWID, SLEEPER_USERNAME
    optional = {
        "ESPN_LEAGUE_ID": ESPN_LEAGUE_ID,
        "ESPN_S2": ESPN_S2,
        "SWID": SWID,
        "SLEEPER_USERNAME": SLEEPER_USERNAME,
    }
    print("\n[4] Optional credentials (needed for Phase 2+):")
    for name, val in optional.items():
        status = "set" if val else "NOT SET (add to .env when ready)"
        print(f"         {name}: {status}")

    # Weights
    weights = DEFAULT_WEIGHTS
    total = sum(weights.values())
    if abs(total - 1.0) < 0.001:
        print(f"\n[5] PASS — default weights sum to 1.0: {weights}")
    else:
        print(f"\n[5] FAIL — weights do not sum to 1.0: {weights} (sum={total})")

    # Gemini model names
    print(f"\n[6] Gemini primary model: {GEMINI_PRIMARY}")
    print(f"    Gemini fallback model: {GEMINI_FALLBACK}")
    print(f"    Max calls per window:  {GEMINI_CALLS_PER_WINDOW}")

    print("\n" + "=" * 50)
    print("CONFIG TEST COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    run_tests()
