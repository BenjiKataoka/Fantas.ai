"""
Tests for Phase 5, Start/Sit advisor.
Covers: injury modifier, lineup selection, FLEX logic, close decisions, offseason guard, router endpoints.
Usage: python3 tests/test_startsit_router.py
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import AsyncMock, MagicMock, patch


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1, Injury modifier unit tests
# ══════════════════════════════════════════════════════════════════════════════

def run_injury_modifier_tests():
    print("=" * 50)
    print("START/SIT, INJURY MODIFIER TESTS")
    print("=" * 50)

    from routers.startsit import _adjusted_proj

    cases = [
        ("Active",       20.0, 20.0,  "Active, no penalty"),
        ("Questionable", 20.0, 17.0,  "Questionable, 15% reduction"),
        ("Doubtful",     20.0, 12.0,  "Doubtful, 40% reduction"),
        ("Out",          20.0,  0.0,  "Out, zeroed"),
        ("IR",           20.0,  0.0,  "IR, zeroed"),
        ("Active",       None,  0.0,  "None projection, treated as 0"),
        (None,           20.0, 20.0,  "None status, defaults to Active"),
        ("Unknown",      20.0, 20.0,  "Unknown status, defaults to Active (1.0x)"),
    ]

    for status, proj, expected, label in cases:
        result = _adjusted_proj(proj, status)
        assert result == expected, f"[{label}] Expected {expected}, got {result}"
        print(f"    PASS, {label} → {result}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2, Close decision detection
# ══════════════════════════════════════════════════════════════════════════════

def run_close_decision_tests():
    print("\n" + "=" * 50)
    print("START/SIT, CLOSE DECISION TESTS")
    print("=" * 50)

    from routers.startsit import _close_decision

    starter = {"player_id": "p1", "name": "Player A", "adjusted_proj": 12.0, "injury_status": "Active"}
    alt     = {"player_id": "p2", "name": "Player B", "adjusted_proj": 10.5, "injury_status": "Active"}

    # [1] Normal close decision
    print("\n[1] Normal close decision (margin 1.5)...")
    result = _close_decision("RB", starter, alt, 1.5)
    assert result["slot"] == "RB"
    assert result["margin"] == 1.5
    assert result["start"]["name"] == "Player A"
    assert result["sit"]["name"] == "Player B"
    assert "matchup" in result["note"]
    print(f"    PASS, note: '{result['note']}'")

    # [2] Injured starter triggers stronger warning
    print("\n[2] Questionable starter, stronger note...")
    inj_starter = {**starter, "injury_status": "Questionable"}
    result2 = _close_decision("WR", inj_starter, alt, 0.8)
    assert "injury" in result2["note"].lower()
    print(f"    PASS, note: '{result2['note']}'")

    # [3] Doubtful starter also triggers injury note
    print("\n[3] Doubtful starter, injury note...")
    dbt_starter = {**starter, "injury_status": "Doubtful"}
    result3 = _close_decision("FLEX", dbt_starter, alt, 1.0)
    assert "injury" in result3["note"].lower()
    print(f"    PASS, note: '{result3['note']}'")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3, Lineup selection logic
# ══════════════════════════════════════════════════════════════════════════════

def run_lineup_logic_tests():
    print("\n" + "=" * 50)
    print("START/SIT, LINEUP LOGIC TESTS")
    print("=" * 50)

    async def _test():
        from routers.startsit import _adjusted_proj, LINEUP_SLOTS, FLEX_POSITIONS, CLOSE_DECISION_MARGIN

        # Build a mock roster: 1 QB, 3 RB, 3 WR, 1 TE, 1 K
        def make_player(pid, name, pos, proj, injury="Active"):
            return {
                "player_id": pid,
                "name": name,
                "position": pos,
                "nfl_team": "PHI",
                "injury_status": injury,
                "injury_detail": None,
                "weighted_proj": proj,
                "adjusted_proj": _adjusted_proj(proj, injury),
                "confidence_flag": "HIGH",
                "sources_used": None,
            }

        players = [
            make_player("qb1", "QB One",   "QB", 26.0),
            make_player("rb1", "RB One",   "RB", 18.0),
            make_player("rb2", "RB Two",   "RB", 14.0),
            make_player("rb3", "RB Three", "RB", 11.0),
            make_player("wr1", "WR One",   "WR", 16.0),
            make_player("wr2", "WR Two",   "WR", 13.0),
            make_player("wr3", "WR Three", "WR",  9.0),
            make_player("te1", "TE One",   "TE", 10.0),
            make_player("k1",  "K One",    "K",   8.0),
        ]

        # [1] Correct starters selected
        print("\n[1] Correct positional starters selected...")
        by_position = {}
        for p in players:
            by_position.setdefault(p["position"], []).append(p)
        for pos in by_position:
            by_position[pos].sort(key=lambda x: x["adjusted_proj"], reverse=True)

        starters = []
        bench_ids = set()
        for pos, count in LINEUP_SLOTS.items():
            pool = by_position.get(pos, [])
            for i in range(min(count, len(pool))):
                starters.append({**pool[i], "slot": pos})
                bench_ids.add(pool[i]["player_id"])

        starter_ids = {s["player_id"] for s in starters}
        assert "qb1" in starter_ids, "QB1 should be started"
        assert "rb1" in starter_ids, "RB1 should be started"
        assert "rb2" in starter_ids, "RB2 should be started"
        assert "rb3" not in starter_ids, "RB3 should not be started (positional)"
        assert "wr1" in starter_ids, "WR1 should be started"
        assert "wr2" in starter_ids, "WR2 should be started"
        assert "te1" in starter_ids, "TE1 should be started"
        assert "k1" in starter_ids, "K1 should be started"
        print(f"    PASS, positional starters: {sorted(starter_ids)}")

        # [2] FLEX picks best remaining RB/WR/TE
        print("\n[2] FLEX selects best remaining RB/WR/TE...")
        flex_pool = sorted(
            [p for pos in FLEX_POSITIONS for p in by_position.get(pos, []) if p["player_id"] not in bench_ids],
            key=lambda x: x["adjusted_proj"],
            reverse=True,
        )
        assert flex_pool[0]["player_id"] == "rb3", f"RB3 (11.0) should be FLEX pick, got {flex_pool[0]['player_id']}"
        print(f"    PASS, FLEX: {flex_pool[0]['name']} ({flex_pool[0]['adjusted_proj']})")

        # [3] Out player is never started
        print("\n[3] Out player never started...")
        players_with_out = [
            make_player("rb1", "RB One",   "RB", 18.0, injury="Out"),
            make_player("rb2", "RB Two",   "RB", 14.0),
            make_player("rb3", "RB Three", "RB", 11.0),
        ]
        by_pos_out = {}
        for p in players_with_out:
            by_pos_out.setdefault(p["position"], []).append(p)
        for pos in by_pos_out:
            by_pos_out[pos].sort(key=lambda x: x["adjusted_proj"], reverse=True)
        # rb1 Out → adjusted_proj=0 → sorts last
        assert by_pos_out["RB"][0]["player_id"] == "rb2", "RB2 should rank first when RB1 is Out"
        assert by_pos_out["RB"][0]["adjusted_proj"] == 14.0
        print(f"    PASS, Out player sinks to bench, RB2 starts")

        # [4] Close decision flagged correctly
        print("\n[4] Close decision flagged when margin < 2.0...")
        close_starters = [
            make_player("rb1", "RB One",   "RB", 12.0),
            make_player("rb2", "RB Two",   "RB", 11.0),  # margin = 1.0 → close
        ]
        margin = close_starters[0]["adjusted_proj"] - close_starters[1]["adjusted_proj"]
        assert margin < CLOSE_DECISION_MARGIN, f"Expected close margin, got {margin}"
        print(f"    PASS, margin {margin} < {CLOSE_DECISION_MARGIN} → flagged as close")

    asyncio.run(_test())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4, Router endpoint tests
# ══════════════════════════════════════════════════════════════════════════════

def run_router_tests():
    print("\n" + "=" * 50)
    print("START/SIT, ROUTER TESTS")
    print("=" * 50)

    from fastapi.testclient import TestClient
    from main import app
    from database import get_db
    from auth import get_current_user

    # Fixed authenticated user so auth doesn't consult the mocked DB in these tests.
    fake_user = MagicMock(id=1, is_approved=True, clerk_id="test")
    def override_current_user():
        return fake_user
    # Apply up front so case [1] (which uses the real DB, not a mocked one) is authed too.
    app.dependency_overrides[get_current_user] = override_current_user

    # [1] Offseason → returns offseason_note, no starters
    print("\n[1] Offseason → offseason_note returned, starters empty...")
    mock_state = {"season": 2026, "season_type": "off", "week": 1}
    with patch("routers.startsit.get_nfl_state", return_value=mock_state):
        with TestClient(app) as client:
            resp = client.get("/api/startsit/1")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
            data = resp.json()
            assert data["offseason_note"] is not None
            assert data["starters"] == []
            assert data["bench"] == []
            assert data["season_type"] == "off"
            print(f"    PASS, offseason_note: '{data['offseason_note'][:60]}...'")

    # [2] In-season, no roster → 404
    print("\n[2] In-season, no roster found → 404...")
    mock_state_regular = {"season": 2025, "season_type": "regular", "week": 5}

    async def mock_db_empty():
        db = AsyncMock()
        # First execute (roster query) returns empty
        empty_result = MagicMock()
        empty_result.all.return_value = []
        db.execute = AsyncMock(return_value=empty_result)
        yield db

    app.dependency_overrides[get_db] = mock_db_empty
    app.dependency_overrides[get_current_user] = override_current_user
    with patch("routers.startsit.get_nfl_state", return_value=mock_state_regular):
        with TestClient(app) as client:
            resp = client.get("/api/startsit/5")
            assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
            assert "roster" in resp.json()["detail"].lower()
            print(f"    PASS, 404 with: {resp.json()['detail']}")
    app.dependency_overrides.clear()

    # [3] In-season, roster present, no projections → 200 with warning
    print("\n[3] In-season roster, no projections → 200 with warning...")

    def make_mock_player(pid, name, pos, inj="Active"):
        p = MagicMock()
        p.player_id = pid
        p.name = name
        p.position = pos
        p.nfl_team = "PHI"
        p.injury_status = inj
        p.injury_detail = None
        return p

    roster_rows = []
    for pid, name, pos in [
        ("qb1", "QB One", "QB"), ("rb1", "RB One", "RB"), ("rb2", "RB Two", "RB"),
        ("wr1", "WR One", "WR"), ("wr2", "WR Two", "WR"), ("te1", "TE One", "TE"),
        ("k1",  "K One",  "K"),
    ]:
        row = MagicMock()
        row.Player = make_mock_player(pid, name, pos)
        row.MyRoster = MagicMock(player_id=pid)
        roster_rows.append(row)

    call_count = {"n": 0}

    async def mock_db_no_proj():
        db = AsyncMock()

        async def mock_execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                # Roster query
                result.all.return_value = roster_rows
            else:
                # Projections query, empty
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute
        yield db

    app.dependency_overrides[get_db] = mock_db_no_proj
    app.dependency_overrides[get_current_user] = override_current_user
    call_count["n"] = 0
    with patch("routers.startsit.get_nfl_state", return_value=mock_state_regular):
        with TestClient(app) as client:
            resp = client.get("/api/startsit/5")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["warning"] is not None
            assert "projection" in data["warning"].lower()
            # All players present (bench + starters), all adjusted_proj = 0 without projections
            total = len(data["starters"]) + len(data["bench"])
            assert total == 7, f"Expected 7 players, got {total}"
            print(f"    PASS, warning: '{data['warning'][:60]}...'")
            print(f"    PASS, {len(data['starters'])} starters, {len(data['bench'])} bench")
    app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_injury_modifier_tests()
    run_close_decision_tests()
    run_lineup_logic_tests()
    run_router_tests()
    print("\n✓ All start/sit tests passed")
