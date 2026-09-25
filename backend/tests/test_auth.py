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


def run_clock_skew_tests():
    """Real signed tokens, real jwt.decode: only the key lookup and issuer are stubbed.
    The azp tests above mock decode entirely, which is why a clock-skew bug got past them."""
    import time
    from cryptography.hazmat.primitives.asymmetric import rsa

    print("\n" + "=" * 50)
    print("AUTH, CLOCK SKEW")
    print("=" * 50)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    iss = "https://test.clerk.accounts.dev"

    def verify(iat_offset: float, lifetime: int = 60):
        now = time.time()
        token = jwt.encode({"sub": "u1", "iss": iss, "iat": int(now + iat_offset),
                            "nbf": int(now + iat_offset) - 10, "exp": int(now + iat_offset) + lifetime},
                           key, algorithm="RS256")
        with patch.object(auth, "_jwks_client") as jwks, patch.object(auth, "_issuer", return_value=iss):
            jwks.return_value.get_signing_key_from_jwt.return_value = MagicMock(key=key.public_key())
            return auth._verify_token(token)

    # What was measured: iat 0.2 to 0.5s ahead of our clock. Round up to a full second.
    assert verify(+1)["sub"] == "u1"
    print("    PASS, a token stamped 1s in our future is accepted")
    assert verify(+4)["sub"] == "u1"
    print("    PASS, 4s of skew is accepted")
    try:
        verify(+30)
        raise AssertionError("a token 30s in the future was accepted")
    except jwt.ImmatureSignatureError:
        print("    PASS, a token 30s in the future is still rejected")
    try:
        verify(-120, lifetime=60)
        raise AssertionError("an expired token was accepted")
    except jwt.ExpiredSignatureError:
        print("    PASS, an expired token is still rejected")


if __name__ == "__main__":
    run_azp_tests()
    run_cors_tests()
    run_clock_skew_tests()
    print("\nALL AUTH TESTS PASSED ✅")
