"""
Settings router, per-user projection weight management.

GET  /api/settings              → current projection weights
PUT  /api/settings              → validates and saves new weights to the users table
GET/PUT/DELETE /api/settings/espn → ESPN cookie status / save (validated) / remove
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator

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


# ── ESPN account (cookies) ────────────────────────────────────────────────────
# Separate from the weights endpoints on purpose: GET /settings must return weights only.
# ponytail: cookies are stored as plain text like the rest of the users table; encrypt at
# rest (e.g. Fernet with a server key) before opening the app beyond a few friends.

class EspnCredentials(BaseModel):
    espn_s2: str
    swid: str

    @field_validator("espn_s2", "swid")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Required")
        return v

    @field_validator("swid")
    @classmethod
    def braced(cls, v: str) -> str:
        # ESPN's SWID cookie is a GUID in braces; people often copy it without them.
        return v if v.startswith("{") else "{" + v.strip("{}") + "}"


@router.get("/settings/espn")
async def get_espn_status(user: User = Depends(get_current_user)):
    """Whether this user has ESPN cookies saved, and whether ESPN has started rejecting them.
    The cookies themselves are never returned."""
    return {"connected": bool(user.espn_s2 and user.swid), "needs_reconnect": user.espn_needs_reconnect}


@router.put("/settings/espn")
async def save_espn_credentials(body: EspnCredentials, user: User = Depends(get_current_user)):
    """Checks the cookies against ESPN before saving, and returns the leagues they unlock."""
    from services.espn_service import EspnAuthError, get_espn_fan_leagues
    from services.projection_service import get_nfl_state

    season = (await get_nfl_state())["season"]
    try:
        leagues = await get_espn_fan_leagues(body.espn_s2, body.swid, season)
    except EspnAuthError:
        raise HTTPException(status_code=400, detail="ESPN didn't accept those cookies. Copy fresh ones from espn.com and try again.")
    user.espn_s2, user.swid, user.espn_needs_reconnect = body.espn_s2, body.swid, False
    logger.info(f"[Settings] ESPN connected for user {user.id}, {len(leagues)} league(s) found")
    return {"connected": True, "leagues": leagues}


@router.delete("/settings/espn")
async def remove_espn_credentials(user: User = Depends(get_current_user)):
    user.espn_s2 = user.swid = None
    user.espn_needs_reconnect = False
    return {"connected": False, "needs_reconnect": False}
