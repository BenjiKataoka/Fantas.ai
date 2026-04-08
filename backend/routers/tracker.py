"""
Player Tracker endpoints.

POST   /api/tracker/star/{player_id}        — star a player, triggers profile generation
DELETE /api/tracker/star/{player_id}        — unstar a player
GET    /api/tracker                         — all starred players with stock profiles
GET    /api/tracker/{player_id}             — single player detail
POST   /api/tracker/refresh/{player_id}     — manually re-run 4-pass analysis

user_id is a placeholder until Clerk auth is wired in Phase 5.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services import tracker_service

router = APIRouter()
logger = logging.getLogger(__name__)

PLACEHOLDER_USER_ID = 1  # replaced with real Clerk auth in Phase 5


@router.post("/tracker/star/{player_id}")
async def star_player(
    player_id: str,
    user_id: int = Query(default=PLACEHOLDER_USER_ID),
    db: AsyncSession = Depends(get_db),
):
    """
    Star a player. Triggers the 4-pass Gemini stock analysis in the background.
    The profile may take 15-30 seconds to generate — poll GET /api/tracker/{player_id}
    and check profile_ready=true.
    """
    result = await tracker_service.star_player(user_id, player_id, db)
    await db.commit()

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("detail"))

    return result


@router.delete("/tracker/star/{player_id}")
async def unstar_player(
    player_id: str,
    user_id: int = Query(default=PLACEHOLDER_USER_ID),
    db: AsyncSession = Depends(get_db),
):
    """Unstar a player (soft delete — stock profile is retained)."""
    result = await tracker_service.unstar_player(user_id, player_id, db)
    await db.commit()

    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Player not starred")

    return result


@router.get("/tracker")
async def get_tracker(
    user_id: int = Query(default=PLACEHOLDER_USER_ID),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all starred players for this user with their stock profiles.
    Sorted by combined_score DESC (highest concern first).
    Players with profile_ready=false have been starred but analysis hasn't completed yet.
    """
    players = await tracker_service.get_tracked_players(user_id, db)
    return {
        "tracked_players": players,
        "total": len(players),
        "user_id": user_id,
    }


@router.get("/tracker/{player_id}")
async def get_tracker_player(
    player_id: str,
    user_id: int = Query(default=PLACEHOLDER_USER_ID),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns full detail for a single tracked player, including historical stats
    by season and the full ADP trend history.
    """
    detail = await tracker_service.get_tracked_player_detail(user_id, player_id, db)
    if not detail:
        raise HTTPException(status_code=404, detail="Player not found in tracker")
    return detail


@router.post("/tracker/refresh/{player_id}")
async def refresh_tracker_player(
    player_id: str,
    user_id: int = Query(default=PLACEHOLDER_USER_ID),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually re-run the 4-pass Gemini analysis for a starred player.
    Use sparingly — each call consumes 4 Gemini API requests.
    """
    success = await tracker_service.refresh_profile(user_id, player_id, db, reason="manual")
    await db.commit()

    if not success:
        raise HTTPException(status_code=404, detail="Player not found in tracker")

    return {"status": "refresh_triggered", "player_id": player_id}
