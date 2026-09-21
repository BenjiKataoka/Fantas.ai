"""
Tests for auth._verify_token's Clerk `azp` (authorized party) check, plus the CORS
origin list. Signature/JWKS are mocked; only the claim policy is under test.
Usage: python3 tests/test_auth.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch

import jwt

import auth


def _verify_with(claims: dict) -> dict:
    with patch.object(auth, "_jwks_client") as jwks, \
         patch.object(auth.jwt, "decode", return_value=claims), \
         patch.object(auth, "ALLOWED_ORIGINS", ["http://localhost:3000", "https://fantas-ai.vercel.app"]):
        jwks.return_value.get_signing_key_from_jwt.return_value = MagicMock(key="k")
        return auth._verify_token("token")


def run_azp_tests():
    print("=" * 50)
    print("AUTH, CLERK azp CHECK")
    print("=" * 50)

    assert _verify_with({"sub": "u1", "azp": "https://fantas-ai.vercel.app"})["sub"] == "u1"
    print("    PASS, allowed origin accepted")

    assert _verify_with({"sub": "u1"})["sub"] == "u1"
    print("    PASS, missing azp accepted (per Clerk docs)")

    try:
        _verify_with({"sub": "u1", "azp": "https://evil.example"})
        raise AssertionError("foreign azp was accepted")
    except jwt.InvalidTokenError:
        print("    PASS, foreign azp rejected")


def run_cors_tests():
    from config import ALLOWED_ORIGINS
    assert not any("*" in o for o in ALLOWED_ORIGINS), "Starlette CORS does not expand wildcards"
    print("    PASS, ALLOWED_ORIGINS has no wildcard entries")


if __name__ == "__main__":
    run_azp_tests()
    run_cors_tests()
    print("\nALL AUTH TESTS PASSED ✅")
