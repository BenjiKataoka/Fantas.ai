"""
Settings router — per-user projection weight management.

GET  /api/settings  → returns current weights for the placeholder user
PUT  /api/settings  → validates and saves new weights to the users table
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)

# Placeholder until Clerk auth is wired in (Phase 5)
PLACEHOLDER_USER_ID = 1


class WeightUpdate(BaseModel):
    weight_sleeper: float
    weight_espn: float
    weight_fp: float

    @field_validator("weight_sleeper", "weight_espn", "weight_fp")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Weights must be non-negative")
        return round(v, 4)

    @model_validator(mode="after")
    def must_sum_to_one(self) -> "WeightUpdate":
        total = round(self.weight_sleeper + self.weight_espn + self.weight_fp, 4)
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0 (got {total})")
        return self


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Returns the current projection weights for the active user."""
    user = await db.get(User, PLACEHOLDER_USER_ID)
    if not user:
        # Return defaults if user row doesn't exist yet
        return {
            "weight_sleeper": 0.35,
            "weight_espn": 0.30,
            "weight_fp": 0.35,
        }
    return {
        "weight_sleeper": user.weight_sleeper,
        "weight_espn": user.weight_espn,
        "weight_fp": user.weight_fp,
    }


@router.put("/settings")
async def update_settings(
    body: WeightUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Updates projection weights for the active user.
    Weights must be non-negative and sum to exactly 1.0.
    """
    user = await db.get(User, PLACEHOLDER_USER_ID)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found. Call /api/roster first to initialize the user.",
        )

    user.weight_sleeper = body.weight_sleeper
    user.weight_espn = body.weight_espn
    user.weight_fp = body.weight_fp

    logger.info(
        f"[Settings] Updated weights for user {PLACEHOLDER_USER_ID}: "
        f"sleeper={body.weight_sleeper} espn={body.weight_espn} fp={body.weight_fp}"
    )

    return {
        "weight_sleeper": user.weight_sleeper,
        "weight_espn": user.weight_espn,
        "weight_fp": user.weight_fp,
        "message": "Weights updated successfully.",
    }
