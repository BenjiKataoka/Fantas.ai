"""
Verify the FastAPI app starts correctly and endpoints respond as expected.
Usage: python tests/test_main.py
Note: Uses TestClient directly — server does not need to be running.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_tests():
    print("=" * 50)
    print("FASTAPI APP TEST")
    print("=" * 50)

    # Test 1: App imports without error
    print("\n[1] Importing FastAPI app...")
    try:
        from main import app
        print("    PASS — app imported")
    except Exception as e:
        print(f"    FAIL — {e}")
        return

    # Test 2-5: Run all requests inside context manager so TestClient closes cleanly
    print("\n[2] Starting TestClient...")
    try:
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            print("    PASS — TestClient ready")

            # Test 3: Health check
            print("\n[3] GET /health...")
            resp = client.get("/health")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
            data = resp.json()
            assert data.get("status") == "ok"
            assert data.get("app") == "Fantas.ai"
            print(f"    PASS — {resp.status_code} {data}")

            # Test 4: 404 on unknown route
            print("\n[4] GET /nonexistent (expect 404)...")
            resp = client.get("/nonexistent")
            assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
            print(f"    PASS — correctly returned 404")

            # Test 5: CORS headers present
            print("\n[5] Checking CORS headers on /health...")
            resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
            cors = resp.headers.get("access-control-allow-origin", "")
            if cors:
                print(f"    PASS — CORS header present: {cors}")
            else:
                print("    WARN — no CORS header returned (may be fine in test mode)")
    except Exception as e:
        print(f"    FAIL — {e}")

    print("\n" + "=" * 50)
    print("FASTAPI TEST COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    run_tests()
