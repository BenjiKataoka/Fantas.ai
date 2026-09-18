"""
Auth-adjacent endpoints:

  GET  /api/me                       — current user's identity + role (any approved user)
  GET  /api/admin/users              — list all users (admin only)
  POST /api/admin/approve/{user_id}  — approve a pending user (admin only)
  POST /api/admin/revoke/{user_id}   — revoke a user's access (admin only)
  GET  /api/admin/llm-usage          — today's Gemini call budget (admin only)

The approval gate: new users are provisioned unapproved and get 403 on every data
endpoint until an admin approves them here.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from auth import get_current_user, require_admin
from config import CLERK_ADMIN_IDS
from services import llm_budget

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """Identity for the signed-in (approved) user. Frontend uses this to gate admin UI."""
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "is_admin": user.clerk_id in CLERK_ADMIN_IDS,
        "is_approved": user.is_approved,
        "sleeper_username": user.sleeper_username,
    }


@router.get("/admin/users")
async def list_users(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """All users, newest first — the approval queue."""
    result = await db.execute(select(User).order_by(User.created_at.desc().nullslast()))
    users = result.scalars().all()
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "is_approved": u.is_approved,
                "is_admin": u.clerk_id in CLERK_ADMIN_IDS,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "approved_at": u.approved_at.isoformat() if u.approved_at else None,
            }
            for u in users
        ]
    }


@router.post("/admin/approve/{user_id}")
async def approve_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_approved = True
    user.approved_at = datetime.utcnow()
    logger.info(f"[Admin] {admin.username} approved user {user_id} ({user.email})")
    return {"status": "approved", "user_id": user_id}


@router.post("/admin/revoke/{user_id}")
async def revoke_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot revoke your own access")
    user.is_approved = False
    user.approved_at = None
    logger.info(f"[Admin] {admin.username} revoked user {user_id} ({user.email})")
    return {"status": "revoked", "user_id": user_id}


@router.get("/admin/llm-usage")
async def llm_usage(admin: User = Depends(require_admin)):
    """Today's Gemini call budget snapshot."""
    return llm_budget.usage()


@router.post("/admin/scheduler/run-market")
async def run_market_refresh(admin: User = Depends(require_admin)):
    """Manually trigger the market refresh now (LLM-free): ESPN position rank + ADP +
    % rostered for every tracked player. Same job the scheduler runs daily."""
    from services.scheduler_service import refresh_market_job
    return await refresh_market_job()
