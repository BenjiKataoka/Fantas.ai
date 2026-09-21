"""
Tests for espn_service.py and projection_service.py.
Usage: python tests/test_espn_service.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run_tests():
    print("=" * 50)
    print("ESPN SERVICE + PROJECTION SERVICE TEST")
    print("=" * 50)

    # ------------------------------------------------------------------ #
    # normalize_name
    # ------------------------------------------------------------------ #
    print("\n[1] Testing normalize_name...")
    try:
        from services.projection_service import normalize_name

        cases = [
            ("Ja'Marr Chase",       "jamarr chase"),
            ("Calvin Ridley Jr.",   "calvin ridley"),
            ("O'Dell Beckham",      "odell beckham"),
            ("Mark Andrews II",     "mark andrews"),
            ("T.J. Hockenson",      "tj hockenson"),
            ("D'Andre Swift",       "dandre swift"),
            ("Patrick Mahomes",     "patrick mahomes"),
            ("Travis Kelce Sr.",    "travis kelce"),
        ]
        all_ok = True
        for raw, expected in cases:
            result = normalize_name(raw)
            status = "PASS" if result == expected else "FAIL"
            if status == "FAIL":
                all_ok = False
            print(f"    {status}, '{raw}' → '{result}' (expected '{expected}')")

        if all_ok:
            print("    All normalize_name cases passed")
    except Exception as e:
        print(f"    FAIL, {e}")

    # ------------------------------------------------------------------ #
    # get_nfl_state
    # ------------------------------------------------------------------ #
    print("\n[2] Fetching NFL state from Sleeper...")
    try:
        from services.projection_service import get_nfl_state
        state = await get_nfl_state()
        print(f"    PASS, week={state['week']} season={state['season']} season_type={state['season_type']}")
        if state["season_type"] == "off":
            print("    NOTE, offseason: projection fetching will be skipped in roster endpoint (expected)")
    except Exception as e:
        print(f"    FAIL, {e}")

    # ------------------------------------------------------------------ #
    # get_espn_projections (public, no auth)
    # ------------------------------------------------------------------ #
    print("\n[3] Fetching ESPN public projections (season=2025, week=1)...")
    try:
        from services.espn_service import get_espn_projections
        projections = await get_espn_projections(season=2025, week=1)
        if projections:
            sample = list(projections.items())[:3]
            print(f"    PASS, {len(projections)} players with projections")
            print(f"    Sample: {sample}")
        else:
            print("    NOTE, 0 projections returned (expected during offseason)")
            print("    PASS, endpoint responded without error")
    except Exception as e:
        print(f"    FAIL, {e}")

    # ------------------------------------------------------------------ #
    # get_espn_roster (requires ESPN credentials in .env)
    # ------------------------------------------------------------------ #
    print("\n[4] ESPN roster sync (requires ESPN_S2 + SWID + ESPN_LEAGUE_ID in .env)...")
    try:
        from config import ESPN_S2, SWID, ESPN_LEAGUE_ID
        if not ESPN_S2 or not SWID or not ESPN_LEAGUE_ID:
            print("    SKIP, ESPN credentials not set in .env (add ESPN_S2, SWID, ESPN_LEAGUE_ID to test)")
        else:
            from services.espn_service import get_espn_roster
            roster = await get_espn_roster(
                league_id=ESPN_LEAGUE_ID,
                espn_s2=ESPN_S2,
                swid=SWID,
                season=2025,
            )
            if roster:
                print(f"    PASS, {len(roster)} players returned from ESPN roster")
                print(f"    Sample: {roster[:2]}")
            else:
                print("    WARN, roster returned empty (check credentials or season year)")
    except Exception as e:
        print(f"    FAIL, {e}")

    print("\n" + "=" * 50)
    print("ESPN SERVICE TEST COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run_tests())
