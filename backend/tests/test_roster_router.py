"""
Verify the /api/leagues and /api/roster endpoints work end-to-end.
Usage: python3 tests/test_roster_router.py
Note: Requires the venv to be active and Neon DB to be reachable.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SLEEPER_USERNAME
assert SLEEPER_USERNAME, "SLEEPER_USERNAME must be set in .env"
# LEAGUE_ID is resolved dynamically for the current season inside run_tests()
# (never hardcode a season-specific league — it breaks on the yearly rollover).
INVALID_LEAGUE_ID = "1180196968005595136"  # Dynasty league — should be rejected


async def run_tests():
    print("=" * 50)
    print("ROSTER ROUTER TEST")
    print("=" * 50)

    # Test 1: /api/leagues returns eligible leagues
    print(f"\n[1] GET /api/leagues?sleeper_username={SLEEPER_USERNAME}")
    try:
        from services.sleeper_service import get_user_id, get_eligible_leagues
        from services.projection_service import get_nfl_state
        from routers.roster import _resolve_league_season
        user_id = await get_user_id(SLEEPER_USERNAME)
        assert user_id, "Could not resolve user_id"
        season = _resolve_league_season(await get_nfl_state())
        leagues = await get_eligible_leagues(user_id, season=season)
        assert isinstance(leagues, list), "Expected a list"
        assert len(leagues) >= 1, "Expected at least 1 eligible league"
        LEAGUE_ID = leagues[0]["league_id"]  # dynamic — first eligible league this season
        print(f"    PASS — {len(leagues)} eligible league(s) for season {season}:")
        for l in leagues:
            print(f"           • {l['name']} ({l['league_id']})")
    except Exception as e:
        print(f"    FAIL — {e}")
        return

    # Test 2: Dynasty league is filtered out
    print(f"\n[2] Confirming dynasty league is excluded...")
    try:
        ids = {l["league_id"] for l in leagues}
        assert INVALID_LEAGUE_ID not in ids, "Dynasty league should not appear in eligible list"
        print(f"    PASS — dynasty league correctly excluded")
    except Exception as e:
        print(f"    FAIL — {e}")

    # Async prep is done. TestClient requests run in a SEPARATE phase (run_client_tests)
    # so they don't share this asyncio.run loop — otherwise asyncpg connections opened in
    # the request handler get stuck on a closed loop (see CLAUDE.md testing conventions).
    return LEAGUE_ID


def run_client_tests(league_id):
    """TestClient phase — runs after the async loop has closed. Uses the context-manager
    form so one anyio portal stays alive across both requests."""
    from fastapi.testclient import TestClient
    from main import app

    # Test 3: /api/roster syncs to DB and returns roster
    print(f"\n[3] GET /api/roster?sleeper_username={SLEEPER_USERNAME}&league_id={league_id}")
    with TestClient(app) as client:
        try:
            resp = client.get(f"/api/roster?sleeper_username={SLEEPER_USERNAME}&league_id={league_id}")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "roster" in data, "Missing 'roster' key"
            assert len(data["roster"]) > 0, "Roster is empty"
            print(f"    PASS — {data['total_players']} players returned, {data['starters']} starters")
            print(f"           season_type={data.get('season_type')} week={data.get('week')}")
            print(f"           First 3 players:")
            for p in data["roster"][:3]:
                print(f"             {p['name']} | {p['position']} | {p['nfl_team']} | starter={p['is_starter']}")

            # Verify projection fields are present on every player (values may be null in offseason)
            proj_keys = {"sleeper_proj", "espn_proj", "fp_proj", "weighted_proj", "confidence_flag"}
            missing = [k for p in data["roster"] for k in proj_keys if k not in p]
            if not missing:
                sample = data["roster"][0]
                print(f"    PASS — projection fields present on all players")
                print(f"           Sample: sleeper={sample['sleeper_proj']} espn={sample['espn_proj']} fp={sample['fp_proj']} weighted={sample['weighted_proj']} confidence={sample['confidence_flag']}")
            else:
                print(f"    FAIL — missing projection keys: {set(missing)}")
        except Exception as e:
            print(f"    FAIL — {e}")
            return

        # Test 6: Invalid league ID is rejected
        print(f"\n[6] GET /api/roster with dynasty league_id (expect 400)...")
        try:
            resp = client.get(f"/api/roster?sleeper_username={SLEEPER_USERNAME}&league_id={INVALID_LEAGUE_ID}")
            assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
            print(f"    PASS — dynasty league correctly rejected with 400")
        except Exception as e:
            print(f"    FAIL — {e}")

    print("\n" + "=" * 50)
    print("ROSTER ROUTER TEST COMPLETE")
    print("=" * 50)


def verify_db():
    """Verify DB state using a sync psycopg2 connection to avoid event loop conflicts."""
    print("\n--- DB VERIFICATION ---")
    import psycopg2
    from config import DATABASE_URL

    # Convert asyncpg URL to psycopg2 format
    sync_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    try:
        conn = psycopg2.connect(sync_url, sslmode="require")
        cur = conn.cursor()

        # Test 4: Players persisted
        print(f"\n[4] Verifying players were saved to Neon...")
        cur.execute("SELECT COUNT(*) FROM players WHERE sleeper_id IS NOT NULL")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"    PASS — {count} players saved in Neon")
        else:
            print(f"    FAIL — no players found in DB")

        # Test 5: my_roster populated
        print(f"\n[5] Verifying my_roster was populated in Neon...")
        cur.execute("SELECT COUNT(*) FROM my_roster WHERE user_id = 1")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"    PASS — {count} roster rows saved in Neon")
        else:
            print(f"    FAIL — no roster rows found")

        cur.close()
        conn.close()
    except Exception as e:
        print(f"    FAIL — {e}")


if __name__ == "__main__":
    league_id = asyncio.run(run_tests())  # async prep; loop closes here
    if league_id:
        run_client_tests(league_id)       # sync TestClient phase, fresh portal
    verify_db()
