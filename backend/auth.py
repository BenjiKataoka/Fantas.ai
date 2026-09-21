"""
Clerk authentication for FastAPI.

Two modes:
  • DEV-FALLBACK (no CLERK_SECRET_KEY set): every request resolves to a single local
    dev user (clerk_id="placeholder", id typically 1) so the app runs without Clerk.
  • REAL AUTH (keys set): verifies the Clerk session JWT from the Authorization header
    against Clerk's JWKS, JIT-provisions the User row, and enforces the approval gate.

Users are provisioned on first authenticated request (is_approved defaults to False,
except admins listed in CLERK_ADMIN_IDS). An unapproved user gets 403 until an admin
approves them, this is the traffic gate.
"""
import base64
import logging
from typing import Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    ALLOWED_ORIGINS,
    AUTH_ENABLED,
    CLERK_ADMIN_IDS,
    CLERK_JWT_ISSUER,
    CLERK_PUBLISHABLE_KEY,
    CLERK_SECRET_KEY,
)
from database import get_db
from models.user import User

logger = logging.getLogger(__name__)

# Dev-fallback identity, reuses the existing placeholder row so local roster/tracker
# data (tied to user_id=1) stays visible when running without Clerk.
DEV_CLERK_ID = "placeholder"
DEV_EMAIL = "placeholder@fantas.ai"
DEV_USERNAME = "dev"

_jwks_client_cache: Optional[PyJWKClient] = None


def _frontend_api_host() -> str:
    """
    Clerk publishable keys embed the Frontend API host: pk_<env>_<base64(host + "$")>.
    Decode it so we can build the JWKS URL / issuer without extra config.
    """
    if not CLERK_PUBLISHABLE_KEY or "_" not in CLERK_PUBLISHABLE_KEY:
        raise RuntimeError("CLERK_PUBLISHABLE_KEY missing or malformed")
    encoded = CLERK_PUBLISHABLE_KEY.split("_", 2)[-1]
    # base64 without padding, add it back
    padded = encoded + "=" * (-len(encoded) % 4)
    host = base64.b64decode(padded).decode().rstrip("$")
    return host


def _issuer() -> str:
    if CLERK_JWT_ISSUER:
        return CLERK_JWT_ISSUER
    return f"https://{_frontend_api_host()}"


def _jwks_client() -> PyJWKClient:
    global _jwks_client_cache
    if _jwks_client_cache is None:
        _jwks_client_cache = PyJWKClient(f"{_issuer()}/.well-known/jwks.json")
    return _jwks_client_cache


def _verify_token(token: str) -> dict:
    """Verify a Clerk session JWT against Clerk's JWKS. Returns the claims."""
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    # Clerk uses `azp` (authorized party), not a standard `aud`, skip aud verification.
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=_issuer(),
        options={"verify_aud": False},
    )
    # Clerk: reject tokens minted for another origin (CSRF guard). Skip only if absent.
    azp = claims.get("azp")
    if azp and azp not in ALLOWED_ORIGINS:
        raise jwt.InvalidTokenError(f"azp {azp!r} not in ALLOWED_ORIGINS")
    return claims


async def _fetch_clerk_user(clerk_id: str) -> tuple[str, str]:
    """
    Look up a user's email + username from Clerk's Backend API (default session tokens
    don't carry email). Falls back to synthesized values if the call fails so
    provisioning never hard-blocks a login.
    """
    fallback = (f"{clerk_id}@clerk.local", clerk_id)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.clerk.com/v1/users/{clerk_id}",
                headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
        emails = data.get("email_addresses") or []
        primary_id = data.get("primary_email_address_id")
        email = next(
            (e["email_address"] for e in emails if e.get("id") == primary_id),
            emails[0]["email_address"] if emails else fallback[0],
        )
        username = data.get("username") or email.split("@")[0]
        return email, username
    except Exception as e:
        logger.error(f"[Auth] Clerk user lookup failed for {clerk_id}: {e}")
        return fallback


async def _get_or_create_user(
    db: AsyncSession,
    clerk_id: str,
    email: str,
    username: str,
    is_admin: bool,
) -> User:
    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    user = result.scalar_one_or_none()
    if user:
        return user

    # Ensure username uniqueness for the rare collision (few users, keep it simple).
    base_username = username or clerk_id
    exists = await db.execute(select(User).where(User.username == base_username))
    if exists.scalar_one_or_none():
        base_username = f"{base_username}_{clerk_id[-4:]}"

    user = User(
        clerk_id=clerk_id,
        email=email,
        username=base_username,
        is_approved=is_admin,  # admins auto-approved; everyone else waits for approval
    )
    db.add(user)
    # Commit immediately: a new unapproved user triggers a 403 below, and that exception
    # would otherwise roll back the whole request session, losing the row and keeping the
    # user out of the admin approval queue forever. (expire_on_commit=False keeps `user` usable.)
    await db.commit()
    logger.info(f"[Auth] Provisioned user clerk_id={clerk_id} approved={is_admin}")
    return user


async def _ensure_dev_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.clerk_id == DEV_CLERK_ID))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(
        clerk_id=DEV_CLERK_ID,
        email=DEV_EMAIL,
        username=DEV_USERNAME,
        is_approved=True,
    )
    db.add(user)
    await db.flush()
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency resolving the authenticated User.
      • Dev-fallback mode → the local dev user.
      • Real mode → verifies the Clerk JWT, provisions the user, enforces approval.
    Raises 401 (no/invalid token) or 403 (awaiting approval).
    """
    if not AUTH_ENABLED:
        return await _ensure_dev_user(db)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()

    try:
        claims = _verify_token(token)
    except Exception as e:
        logger.warning(f"[Auth] Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    clerk_id = claims.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    is_admin = clerk_id in CLERK_ADMIN_IDS
    # Prefer email from claims (if a JWT template adds it); otherwise ask Clerk's API.
    email = claims.get("email")
    username = claims.get("username")
    if not email:
        email, username = await _fetch_clerk_user(clerk_id)

    user = await _get_or_create_user(db, clerk_id, email, username or email.split("@")[0], is_admin)

    # Admins are always approved, heals the case where the row was created before the
    # user was added to CLERK_ADMIN_IDS (first-admin bootstrap).
    if is_admin and not user.is_approved:
        from datetime import datetime
        user.is_approved = True
        user.approved_at = datetime.utcnow()

    if not user.is_approved:
        raise HTTPException(
            status_code=403,
            detail="Your account is awaiting admin approval.",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency for admin-only endpoints."""
    if user.clerk_id not in CLERK_ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
