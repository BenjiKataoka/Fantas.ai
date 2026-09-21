"""
Tests for waiver_service (pure logic, hand-checked numbers).
Usage: python3 tests/test_waiver_service.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.waiver_service import rank_free_agents

SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "BN", "BN"]


def P(pid, pos, proj):
    return {"player_id": pid, "name": pid, "position": pos, "proj": proj}


def run_tests():
    print("=" * 50); print("WAIVERS, RANK FREE AGENTS"); print("=" * 50)
    roster = [P("qb", "QB", 20), P("rb1", "RB", 14), P("rb2", "RB", 6), P("wr1", "WR", 12), P("te", "TE", 5)]
    # Base lineup: qb, rb1, wr1, te, FLEX=rb2 (6).
    fas = [P("wr_hot", "WR", 11), P("te_up", "TE", 8), P("qb_bad", "QB", 15), P("rb_meh", "RB", 4)]
    by_id = {p["player_id"]: p for p in rank_free_agents(fas, roster, SLOTS)}

    assert by_id["wr_hot"]["upgrade"] == 5.0 and by_id["wr_hot"]["replaces"]["player_id"] == "rb2", by_id["wr_hot"]
    print("    PASS, a WR can win the FLEX spot (11 over rb2's 6)")
    assert by_id["te_up"]["upgrade"] == 3.0 and by_id["te_up"]["replaces"]["player_id"] == "te"
    print("    PASS, same-position upgrade at TE")
    assert by_id["qb_bad"]["upgrade"] == 0 and by_id["qb_bad"]["replaces"] is None
    assert by_id["rb_meh"]["upgrade"] == 0
    print("    PASS, players who beat nobody are depth only")

    order = [p["player_id"] for p in rank_free_agents(fas, roster, SLOTS)]
    assert order[:2] == ["wr_hot", "te_up"], order
    print("    PASS, ranked by upgrade first")

    # Empty slot: no TE rostered, any TE is a gain with nobody replaced.
    r = rank_free_agents([P("te_any", "TE", 3)], [p for p in roster if p["position"] != "TE"], SLOTS)[0]
    assert r["upgrade"] == 3.0 and r["replaces"] is None, r
    print("    PASS, filling an empty slot counts as an upgrade")

    many = [P(f"k{i}", "K", i) for i in range(20)]
    assert len(rank_free_agents(many, roster, SLOTS, per_position=5)) == 5
    print("    PASS, capped per position")


if __name__ == "__main__":
    run_tests()
    print("\nALL WAIVER TESTS PASSED")
