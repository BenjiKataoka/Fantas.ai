"""
Tests for portfolio_service (pure aggregation, hand-checked numbers).
Usage: python3 tests/test_portfolio_service.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.portfolio_service import build_portfolio


def R(pid, league, starter, name=None, pos="WR"):
    return {"player_id": pid, "name": name or pid, "position": pos, "nfl_team": "HOU", "injury_status": None,
            "is_starter": starter, "slot": "WR" if starter else "BN",
            "league_id": league, "platform": "SLEEPER", "league_name": f"League {league}"}


def run_tests():
    print("=" * 50); print("PORTFOLIO, BUILD"); print("=" * 50)
    rows = [R("nico", "A", True), R("nico", "B", True), R("nico", "C", False),
            R("puka", "A", True), R("ladd", "B", False)]
    proj = {"nico": {"weighted_proj": 13.5}, "puka": {"weighted_proj": 20.0}}
    out = build_portfolio(rows, proj, {}, league_count=3)
    by = {p["player_id"]: p for p in out["players"]}

    assert len(out["players"]) == 3, out["players"]
    assert by["nico"]["held"] == 3 and by["nico"]["starting"] == 2
    assert [l["league_id"] for l in by["nico"]["leagues"]] == ["A", "B", "C"], "starters first"
    print("    PASS, one row per player; held 3, starting 2; starting leagues listed first")

    assert [p["player_id"] for p in out["players"]] == ["nico", "puka", "ladd"], "by starting, then held, then proj"
    print("    PASS, ranked by lineups started, then leagues held, then projection")

    s = out["summary"]
    assert s == {"leagues": 3, "players": 3, "starting_slots": 3, "projected_points": 13.5 * 2 + 20.0,
                 "biggest_exposure": {"player_id": "nico", "name": "nico", "held": 3}}, s
    print("    PASS, summary: projected points count each lineup a player starts in")

    solo = build_portfolio([R("a", "A", True), R("b", "A", False)], {}, {}, league_count=1)["summary"]
    assert solo["biggest_exposure"] is None and solo["projected_points"] == 0
    print("    PASS, no 'biggest exposure' callout when nobody is on two teams")

    assert build_portfolio([], {}, {}, league_count=0)["players"] == []
    print("    PASS, empty portfolio")


if __name__ == "__main__":
    run_tests()
    print("\nALL PORTFOLIO TESTS PASSED")
