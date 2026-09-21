"""
Tests for recap_service (pure logic, hand-checked numbers).
Usage: python3 tests/test_recap_service.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.recap_service import best_lineup, build_recap

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF", "BN", "BN"]


def P(pid, pos, pts):
    return {"player_id": pid, "position": pos, "actual": pts}


def run_lineup_tests():
    print("=" * 50); print("RECAP, BEST LINEUP"); print("=" * 50)
    pool = [P("qb", "QB", 20), P("rb1", "RB", 15), P("rb2", "RB", 10), P("rb3", "RB", 9),
            P("wr1", "WR", 12), P("wr2", "WR", 3), P("te", "TE", 8), P("k", "K", 7), P("DEN", "DEF", 5)]
    lu = best_lineup(pool, SLOTS, lambda p: p["actual"])
    by_slot = {p["slot"]: p["player_id"] for p in lu}
    assert len(lu) == 9, lu                                  # BN slots ignored
    assert by_slot["FLEX"] == "rb3", by_slot                # best leftover flex (9 > wr2's 3)
    assert by_slot["DEF"] == "DEN" and by_slot["K"] == "k"
    assert sum(p["actual"] for p in lu) == 20 + 15 + 10 + 12 + 3 + 8 + 9 + 7 + 5
    print("    PASS, fills every slot incl. DEF; FLEX takes best leftover")

    # A narrow slot must not lose its only player to FLEX.
    lu = best_lineup([P("te", "TE", 30), P("wr", "WR", 1)], ["FLEX", "TE"], lambda p: p["actual"])
    assert {p["slot"]: p["player_id"] for p in lu} == {"TE": "te", "FLEX": "wr"}, lu
    print("    PASS, narrow slots are filled before flex")


def run_recap_tests():
    print("\n" + "=" * 50); print("RECAP, BUILD"); print("=" * 50)
    matchup = {
        "starters": ["qb", "rb1", "wr1"],
        "players": ["qb", "rb1", "wr1", "rb2"],
        "players_points": {"qb": 20.0, "rb1": 5.0, "wr1": 10.0, "rb2": 25.0},
    }
    proj = {
        "qb":  {"sleeper": 18, "espn": 22, "fp": None, "weighted": 20},
        "rb1": {"sleeper": 12, "espn": 10, "fp": None, "weighted": 11},
        "wr1": {"sleeper": 10, "espn": 14, "fp": None, "weighted": 12},
        "rb2": {"sleeper": 9,  "espn": 8,  "fp": None, "weighted": 8},
    }
    info = {k: {"name": k.upper(), "position": pos} for k, pos in
            [("qb", "QB"), ("rb1", "RB"), ("wr1", "WR"), ("rb2", "RB")]}
    r = build_recap(matchup, ["QB", "RB", "WR", "BN"], proj, info, week=2, season=2026, final=True)

    lu = r["lineup"]
    assert lu["your_points"] == 35.0, lu                        # 20 + 5 + 10
    assert lu["best_possible_points"] == 55.0, lu               # rb2 (25) should have started
    assert lu["points_left_on_bench"] == 20.0, lu
    assert lu["projection_lineup_points"] == 35.0, lu           # projections also picked rb1
    print(f"    PASS, lineup math: {lu['your_points']} scored, {lu['points_left_on_bench']} left on bench")

    # sleeper errors: 2, 7, 0, 16 -> 6.25 ; espn: 2, 5, 4, 17 -> 7.0 ; fp has no data
    assert r["accuracy"]["sleeper"] == {"mae": 6.25, "n": 4}, r["accuracy"]
    assert r["accuracy"]["espn"] == {"mae": 7.0, "n": 4}
    assert r["accuracy"]["fp"] == {"mae": None, "n": 0}
    assert r["most_accurate_source"] == "sleeper"
    print("    PASS, per-source MAE + most accurate source")

    assert [p["player_id"] for p in r["players"]] == ["qb", "rb1", "wr1", "rb2"]  # starters first
    assert r["players"][1]["diff"] == -6.0                      # rb1: 5 actual - 11 weighted
    print("    PASS, starters listed first, diff = actual - weighted")

    # Team defense ids are letters; position is inferred when not in the DB.
    r = build_recap({"starters": ["DEN"], "players": ["DEN"], "players_points": {"DEN": 7}},
                    ["DEF"], {}, {}, week=1, season=2026, final=True)
    assert r["players"][0]["position"] == "DEF" and r["lineup"]["best_possible_points"] == 7
    assert r["most_accurate_source"] is None                    # no projections, no winner
    print("    PASS, DEF inferred; no projections -> no accuracy winner")


if __name__ == "__main__":
    run_lineup_tests()
    run_recap_tests()
    print("\nALL RECAP TESTS PASSED ✅")
