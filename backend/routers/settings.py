"""
Settings router, per-user projection weight management.

GET  /api/settings  → returns current weights for the placeholder user
PUT  /api/settings  → validates and saves new weights to the users table
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


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
async def get_settings(user: User = Depends(get_current_user)):
    """Returns the current projection weights for the active user."""
    return {
        "weight_sleeper": user.weight_sleeper,
        "weight_espn": user.weight_espn,
        "weight_fp": user.weight_fp,
    }


@router.put("/settings")
async def update_settings(
    body: WeightUpdate,
    user: User = Depends(get_current_user),
):
    """
    Updates projection weights for the active user.
    Weights must be non-negative and sum to exactly 1.0.
    """
    user.weight_sleeper = body.weight_sleeper
    user.weight_espn = body.weight_espn
    user.weight_fp = body.weight_fp

    logger.info(
        f"[Settings] Updated weights for user {user.id}: "
        f"sleeper={body.weight_sleeper} espn={body.weight_espn} fp={body.weight_fp}"
    )

    # Return the same shape as GET (weights only), a mixed-in message field would
    # pollute the frontend weights object and break slider redistribution.
    return {
        "weight_sleeper": user.weight_sleeper,
        "weight_espn": user.weight_espn,
        "weight_fp": user.weight_fp,
    }
