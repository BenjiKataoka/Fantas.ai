"""
Tests for matchup_service's pure logic (hand-checked).
Usage: python3 tests/test_matchup_service.py
"""
import os
import sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.matchup_service import group_needs, kickoff_windows, lineup_issues, team_score, win_probability

SUN1 = datetime(2026, 9, 27, 17, 0, tzinfo=timezone.utc)
SNF = datetime(2026, 9, 28, 0, 20, tzinfo=timezone.utc)
SCHEDULE = {"HOU": {"kickoff": SUN1, "state": "pre"}, "TB": {"kickoff": SUN1, "state": "pre"},
            "KC": {"kickoff": SNF, "state": "pre"}}  # DAL not in it: on bye
LEAGUE = {"league_id": "L1", "platform": "SLEEPER", "name": "League One", "url": "u"}


def P(pid, pos, team, proj, status="Active", slot=None):
    return {"player_id": pid, "name": pid, "position": pos, "nfl_team": team, "proj": proj,
            "injury_status": status, "slot": slot or pos}


def run_tests():
    print("=" * 50); print("MATCHUPS, PURE LOGIC"); print("=" * 50)
    assert win_probability(100, 100) == 0.5
    assert win_probability(125, 100) > 0.8 and win_probability(100, 125) < 0.2
    print("    PASS, win probability: even at a tie, ~84% when up a full spread")

    starters = [P("qb", "QB", "KC", 20), P("wr_out", "WR", "HOU", 15, "Out"), P("te_bye", "TE", "DAL", 9),
                P("rb_q", "RB", "TB", 12, "Questionable")]
    assert team_score(starters, SCHEDULE) == 32.0, team_score(starters, SCHEDULE)
    print("    PASS, team score drops the Out player and the one on bye, keeps the questionable one")

    bench = [P("wr_bench", "WR", "TB", 8, slot="BN"), P("wr_bye", "WR", "DAL", 30, slot="BN"),
             P("te_bench", "TE", "KC", 6, slot="BN")]
    empty = {"player_id": None, "name": None, "position": None, "slot": "FLEX", "proj": 0}
    issues = lineup_issues(LEAGUE, starters + [empty], bench, SCHEDULE)
    by = {i["title"]: i for i in issues}
    assert by["wr_out is Out and in your lineup"]["swap"]["player_id"] == "wr_bench", "skips the bench WR on bye"
    assert by["te_bye is on bye and in your lineup"]["swap"]["player_id"] == "te_bench"
    assert by["Your FLEX spot is empty"]["swap"] is None, "bench already used up"
    assert by["rb_q is Questionable"]["severity"] == "warn" and by["rb_q is Questionable"]["swap"] is None
    print("    PASS, out / bye / empty get a legal healthy swap, never the same bench player twice")

    L2 = {**LEAGUE, "league_id": "L2", "name": "League Two"}
    grouped = group_needs(issues + lineup_issues(L2, [P("rb_q", "RB", "TB", 12, "Questionable")], [], SCHEDULE))
    warns = [g for g in grouped if g["severity"] == "warn"]
    assert len(warns) == 1 and warns[0]["league_name"] == "League One, League Two", warns
    assert grouped[0]["severity"] == "out", "outs first"
    print("    PASS, a questionable player in two lineups is one line naming both")

    wins = kickoff_windows(starters + [P("qb", "QB", "KC", 20)], SCHEDULE)
    assert [(w["count"], w["players"]) for w in wins] == [(1, ["rb_q"]), (1, ["qb"])], wins
    assert wins[0]["label"] == "Sun 1:00 PM" and wins[1]["label"] == "Sun 8:20 PM", wins
    print("    PASS, kickoff windows in Eastern time, each player once, out and bye players left out")


if __name__ == "__main__":
    run_tests()
    print("\nALL MATCHUP TESTS PASSED")
