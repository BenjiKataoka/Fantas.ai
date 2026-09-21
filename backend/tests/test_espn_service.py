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


def run_multi_league_tests():
    """Pure helpers for ESPN leagues (no network), shapes taken from real 2026 responses."""
    from services.espn_service import (espn_is_redraft_ppr, espn_my_team, espn_roster_positions,
                                       espn_to_sleeper_ids)
    print("\n" + "=" * 50); print("ESPN, MULTI-LEAGUE HELPERS"); print("=" * 50)

    league = {
        "settings": {
            "rosterSettings": {"lineupSlotCounts": {"0": 1, "2": 2, "4": 2, "6": 1, "7": 1, "16": 1,
                                                    "17": 1, "20": 7, "21": 1, "23": 1, "8": 0}},
            "scoringSettings": {"scoringItems": [{"statId": 53, "points": 1.0}]},
            "draftSettings": {"keeperCount": 0},
        },
        "teams": [{"id": 1, "owners": ["{AAA-1}"]}, {"id": 2, "owners": ["{bbb-2}", "{CCC-3}"]}],
    }
    slots = espn_roster_positions(league)
    assert sorted(slots) == sorted(["QB", "RB", "RB", "WR", "WR", "TE", "SUPER_FLEX", "DEF", "K", "FLEX"]), slots
    print("    PASS, slots mapped; bench/IR dropped; OP → SUPER_FLEX")

    assert espn_is_redraft_ppr(league)
    half = {"settings": {**league["settings"], "scoringSettings": {"scoringItems": [{"statId": 53, "points": 0.5}]}}}
    keeper = {"settings": {**league["settings"], "draftSettings": {"keeperCount": 2}}}
    assert not espn_is_redraft_ppr(half) and not espn_is_redraft_ppr(keeper)
    print("    PASS, PPR redraft accepted; half-PPR and keeper rejected")

    assert espn_my_team(league, "{ccc-3}")["id"] == 2 and espn_my_team(league, "CCC-3")["id"] == 2
    assert espn_my_team(league, "{zzz}") is None
    assert espn_my_team(league, team_id=1)["id"] == 1 and espn_my_team(league, "{ccc-3}", team_id=1)["id"] == 1
    assert espn_my_team(league) is None
    print("    PASS, team found by SWID regardless of braces/case; a picked team_id wins")

    all_players = {
        "4881": {"espn_id": 4362238, "full_name": "Puka Nacua", "position": "WR"},
        "9999": {"espn_id": None, "full_name": "Bucky Irving", "position": "RB"},
    }
    entry = lambda pid, name, pos: {"lineupSlotId": 4, "playerPoolEntry": {"player": {"id": pid, "fullName": name, "defaultPositionId": pos}}}
    matched = espn_to_sleeper_ids([entry(4362238, "Puka Nacua", 3), entry(1, "Bucky Irving", 2),
                                   entry(-16002, "Bills D/ST", 16)], all_players)
    assert [pid for pid, _ in matched] == ["4881", "9999"], matched
    print("    PASS, matched by espn_id, then name + position; D/ST dropped")


if __name__ == "__main__":
    run_multi_league_tests()
    asyncio.run(run_tests())
