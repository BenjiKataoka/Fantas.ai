"""
Tests for projection_engine.py and the settings + projections endpoints.
Usage: python3 tests/test_projection_engine.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SLEEPER_USERNAME
assert SLEEPER_USERNAME, "SLEEPER_USERNAME must be set in .env"

LEAGUE_ID = "1221322522297901056"


def run_unit_tests():
    from services.projection_engine import compute_weighted_projection

    print("=" * 50)
    print("PROJECTION ENGINE — UNIT TESTS")
    print("=" * 50)

    # ------------------------------------------------------------------ #
    # [1] All 3 sources present — HIGH confidence
    # ------------------------------------------------------------------ #
    print("\n[1] All 3 sources present (HIGH confidence)...")
    result = compute_weighted_projection(20.0, 18.0, 22.0)
    assert result["confidence_flag"] == "HIGH", f"Expected HIGH, got {result['confidence_flag']}"
    assert result["weighted_proj"] is not None
    assert abs(sum(result["sources_used"].values()) - 1.0) < 0.001, "Weights must sum to 1.0"
    expected = round(20.0 * 0.35 + 18.0 * 0.30 + 22.0 * 0.35, 2)
    assert result["weighted_proj"] == expected, f"Expected {expected}, got {result['weighted_proj']}"
    print(f"    PASS — weighted={result['weighted_proj']} sources={result['sources_used']}")

    # ------------------------------------------------------------------ #
    # [2] One source missing — weight redistributed, MEDIUM confidence
    # ------------------------------------------------------------------ #
    print("\n[2] ESPN missing — weight redistributed (MEDIUM confidence)...")
    result = compute_weighted_projection(20.0, None, 22.0)
    assert result["confidence_flag"] == "MEDIUM"
    assert "espn" not in result["sources_used"]
    assert abs(sum(result["sources_used"].values()) - 1.0) < 0.001
    # sleeper=0.35, fp=0.35 → each gets 0.5 after redistribution
    assert result["sources_used"]["sleeper"] == 0.5
    assert result["sources_used"]["fp"] == 0.5
    expected = round(20.0 * 0.5 + 22.0 * 0.5, 2)
    assert result["weighted_proj"] == expected
    print(f"    PASS — weighted={result['weighted_proj']} sources={result['sources_used']}")

    # ------------------------------------------------------------------ #
    # [3] Two sources missing — LOW confidence
    # ------------------------------------------------------------------ #
    print("\n[3] Only Sleeper available (LOW confidence)...")
    result = compute_weighted_projection(20.0, None, None)
    assert result["confidence_flag"] == "LOW"
    assert result["sources_used"] == {"sleeper": 1.0}
    assert result["weighted_proj"] == 20.0
    print(f"    PASS — weighted={result['weighted_proj']} confidence={result['confidence_flag']}")

    # ------------------------------------------------------------------ #
    # [4] All sources missing — returns all None
    # ------------------------------------------------------------------ #
    print("\n[4] All sources None (offseason)...")
    result = compute_weighted_projection(None, None, None)
    assert result["weighted_proj"] is None
    assert result["sources_used"] is None
    assert result["confidence_flag"] is None
    print(f"    PASS — all fields None as expected")

    # ------------------------------------------------------------------ #
    # [5] Custom per-user weights
    # ------------------------------------------------------------------ #
    print("\n[5] Custom weights (sleeper=0.5, espn=0.2, fp=0.3)...")
    custom = {"sleeper": 0.5, "espn": 0.2, "fp": 0.3}
    result = compute_weighted_projection(20.0, 18.0, 22.0, weights=custom)
    expected = round(20.0 * 0.5 + 18.0 * 0.2 + 22.0 * 0.3, 2)
    assert result["weighted_proj"] == expected, f"Expected {expected}, got {result['weighted_proj']}"
    assert result["confidence_flag"] == "HIGH"
    print(f"    PASS — weighted={result['weighted_proj']} (expected {expected})")

    # ------------------------------------------------------------------ #
    # [6] Custom weights with missing source — redistributes correctly
    # ------------------------------------------------------------------ #
    print("\n[6] Custom weights (0.5/0.2/0.3) with ESPN missing...")
    result = compute_weighted_projection(20.0, None, 22.0, weights=custom)
    # sleeper=0.5, fp=0.3 → total=0.8 → sleeper=0.625, fp=0.375
    assert abs(result["sources_used"]["sleeper"] - round(0.5 / 0.8, 4)) < 0.001
    assert abs(result["sources_used"]["fp"] - round(0.3 / 0.8, 4)) < 0.001
    assert result["confidence_flag"] == "MEDIUM"
    print(f"    PASS — redistributed weights: {result['sources_used']}")

    print("\n    All unit tests passed.")


def run_endpoint_tests():
    """
    TestClient is used as a context manager so all requests share one anyio portal
    and one event loop. This keeps asyncpg connections valid across multiple calls.
    Never wrap this function in asyncio.run() — TestClient manages the loop internally.
    """
    print("\n" + "=" * 50)
    print("SETTINGS + PROJECTIONS ENDPOINT TESTS")
    print("=" * 50)

    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as client:
        # ------------------------------------------------------------------ #
        # Seed: ensure user row exists before settings tests
        # ------------------------------------------------------------------ #
        client.get(f"/api/roster?sleeper_username={SLEEPER_USERNAME}&league_id={LEAGUE_ID}")

        # ------------------------------------------------------------------ #
        # [7] GET /api/settings — returns weights
        # ------------------------------------------------------------------ #
        print("\n[7] GET /api/settings...")
        try:
            resp = client.get("/api/settings")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "weight_sleeper" in data and "weight_espn" in data and "weight_fp" in data
            print(f"    PASS — sleeper={data['weight_sleeper']} espn={data['weight_espn']} fp={data['weight_fp']}")
        except Exception as e:
            print(f"    FAIL — {e}")

        # ------------------------------------------------------------------ #
        # [8] PUT /api/settings — updates weights
        # ------------------------------------------------------------------ #
        print("\n[8] PUT /api/settings with valid weights (0.5/0.2/0.3)...")
        try:
            resp = client.put("/api/settings", json={
                "weight_sleeper": 0.5,
                "weight_espn": 0.2,
                "weight_fp": 0.3,
            })
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["weight_sleeper"] == 0.5
            assert data["weight_espn"] == 0.2
            assert data["weight_fp"] == 0.3
            print(f"    PASS — weights saved: {data['weight_sleeper']}/{data['weight_espn']}/{data['weight_fp']}")
        except Exception as e:
            print(f"    FAIL — {e}")

        # ------------------------------------------------------------------ #
        # [9] PUT /api/settings — rejects weights that don't sum to 1.0
        # ------------------------------------------------------------------ #
        print("\n[9] PUT /api/settings with invalid weights (don't sum to 1.0)...")
        try:
            resp = client.put("/api/settings", json={
                "weight_sleeper": 0.5,
                "weight_espn": 0.5,
                "weight_fp": 0.5,
            })
            assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"
            print(f"    PASS — correctly rejected with 422")
        except Exception as e:
            print(f"    FAIL — {e}")

        # ------------------------------------------------------------------ #
        # [10] GET /api/settings — reflects the saved values from test [8]
        # ------------------------------------------------------------------ #
        print("\n[10] GET /api/settings — verify saved weights persist...")
        try:
            resp = client.get("/api/settings")
            data = resp.json()
            assert data["weight_sleeper"] == 0.5
            assert data["weight_espn"] == 0.2
            assert data["weight_fp"] == 0.3
            print(f"    PASS — weights persisted correctly")
        except Exception as e:
            print(f"    FAIL — {e}")

        # ------------------------------------------------------------------ #
        # [11] GET /api/projections/{week} — returns projection fields
        # ------------------------------------------------------------------ #
        print("\n[11] GET /api/projections/1 (offseason — expect null projections)...")
        try:
            resp = client.get("/api/projections/1")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "projections" in data
            assert "weights_used" in data
            assert "season_type" in data
            print(f"    PASS — {len(data['projections'])} players returned, season_type={data['season_type']}")
            if data["projections"]:
                sample = data["projections"][0]
                proj_keys = {"sleeper_proj", "espn_proj", "fp_proj", "weighted_proj", "confidence_flag"}
                assert proj_keys.issubset(sample.keys()), f"Missing keys: {proj_keys - sample.keys()}"
                print(f"    PASS — all projection keys present on players")
                print(f"           Sample: {sample['name']} | weighted={sample['weighted_proj']} | confidence={sample['confidence_flag']}")
                print(f"           Weights used: {data['weights_used']}")
        except Exception as e:
            print(f"    FAIL — {e}")

        # ------------------------------------------------------------------ #
        # [12] GET /api/projections/{week} — invalid week rejected
        # ------------------------------------------------------------------ #
        print("\n[12] GET /api/projections/0 (invalid week — expect 400)...")
        try:
            resp = client.get("/api/projections/0")
            assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
            print(f"    PASS — correctly rejected with 400")
        except Exception as e:
            print(f"    FAIL — {e}")

        # Restore default weights so other tests aren't affected
        client.put("/api/settings", json={
            "weight_sleeper": 0.35,
            "weight_espn": 0.30,
            "weight_fp": 0.35,
        })

    print("\n" + "=" * 50)
    print("PROJECTION ENGINE TEST COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    run_unit_tests()
    # TestClient manages its own event loop — never wrap in asyncio.run()
    run_endpoint_tests()
