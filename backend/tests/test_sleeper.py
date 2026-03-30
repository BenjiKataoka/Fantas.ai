"""
Run this to verify Sleeper API is working end-to-end.
Usage: python test_sleeper.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SLEEPER_USERNAME
from services.sleeper_service import (
    get_user_id,
    get_leagues,
    get_roster,
    get_trending_players,
    get_projections,
    CURRENT_SEASON,
)

assert SLEEPER_USERNAME, "SLEEPER_USERNAME must be set in .env"
USERNAME = SLEEPER_USERNAME


async def run_tests():
    print("=" * 50)
    print("SLEEPER API TEST")
    print("=" * 50)

    # Test 1: Resolve username → user_id
    print(f"\n[1] Fetching user_id for '{USERNAME}'...")
    user_id = await get_user_id(USERNAME)
    if not user_id:
        print("  FAIL — could not resolve username. Check spelling or Sleeper API.")
        return
    print(f"  PASS — user_id: {user_id}")

    # Test 2: Get leagues
    print(f"\n[2] Fetching leagues for season {CURRENT_SEASON}...")
    leagues = await get_leagues(user_id, CURRENT_SEASON)
    if not leagues:
        print(f"  WARN — no leagues found for season {CURRENT_SEASON}.")
        print("         This is expected in the offseason if no league is active yet.")
    else:
        print(f"  PASS — found {len(leagues)} league(s):")
        for league in leagues:
            print(f"         • {league.get('name')} (id: {league.get('league_id')}, "
                  f"scoring: {league.get('scoring_settings', {}).get('rec', 'N/A')} rec)")

    # Test 3: Get roster from first league
    if leagues:
        first_league = leagues[0]
        league_id = first_league.get("league_id")
        print(f"\n[3] Fetching your roster from league '{first_league.get('name')}'...")
        roster = await get_roster(league_id, user_id)
        if not roster:
            print("  FAIL — roster not found. Your user_id may not match an owner in this league.")
        else:
            player_ids = roster.get("players", [])
            starters = roster.get("starters", [])
            print(f"  PASS — roster has {len(player_ids)} players, {len(starters)} starters")
            print(f"         First 5 player IDs: {player_ids[:5]}")

        # Test 4: Get projections for week 1
        print(f"\n[4] Fetching Sleeper projections for {CURRENT_SEASON} week 1...")
        projections = await get_projections(CURRENT_SEASON, 1)
        if not projections:
            print("  WARN — no projections returned. May be offseason.")
        else:
            sample = list(projections.items())[:3]
            print(f"  PASS — got projections for {len(projections)} players")
            print(f"         Sample (player_id → pts_ppr):")
            for pid, proj in sample:
                pts = proj.get("pts_ppr", "N/A")
                print(f"           {pid}: {pts}")
    else:
        print("\n[3] Skipping roster test — no leagues found.")
        print("[4] Skipping projections test — no leagues found.")

    # Test 5: Trending adds
    print("\n[5] Fetching trending adds...")
    trending = await get_trending_players("add", limit=5)
    if not trending:
        print("  FAIL — no trending players returned.")
    else:
        print(f"  PASS — top 5 trending adds:")
        for t in trending:
            print(f"         player_id: {t.get('player_id')}, adds: {t.get('count')}")

    print("\n" + "=" * 50)
    print("TEST COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run_tests())
