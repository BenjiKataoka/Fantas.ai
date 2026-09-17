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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.player import Player
from models.user import User
from auth import get_current_user
from services import tracker_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/players/search")
async def search_players(
    q: str = Query(..., min_length=2, description="Player name search query"),
    limit: int = Query(default=25, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Search all NFL players by name (case-insensitive partial match).

    Primary source: Sleeper's full player map (~10k players, cached 24h).
    Falls back to local DB if the Sleeper cache is cold (roster not yet loaded).
    Ensures the matched players exist in the local DB so they can be starred.
    """
    from services.sleeper_service import get_all_players
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    q_lower = q.lower()

    RELEVANT_POSITIONS = {"QB", "RB", "WR", "TE", "K"}

    # --- Try Sleeper's full player map first (cached 24h) ---
    all_players = await get_all_players()
    matched = []
    if all_players:
        for pid, p in all_players.items():
            name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            pos  = p.get("position", "")
            if pos not in RELEVANT_POSITIONS:
                continue
            if q_lower in name.lower():
                matched.append({
                    "player_id": pid,
                    "name":      name,
                    "position":  pos,
                    "nfl_team":  p.get("team") or p.get("nfl_team"),
                    "espn_id":   str(p["espn_id"]) if p.get("espn_id") is not None else None,
                })
        # Sort by relevance: last name starts with query > name contains query, then alpha
        def relevance(m: dict) -> tuple:
            name_lower = m["name"].lower()
            last = name_lower.split()[-1] if name_lower else ""
            starts_with = last.startswith(q_lower) or name_lower.startswith(q_lower)
            return (0 if starts_with else 1, name_lower)

        matched.sort(key=relevance)
        matched = matched[:limit]

        # Upsert matched players so they're star-able
        if matched:
            stmt = pg_insert(Player).values([
                {
                    "player_id":      m["player_id"],
                    "name":           m["name"],
                    "position":       m["position"],
                    "nfl_team":       m["nfl_team"],
                    "sleeper_id":     m["player_id"],
                    "espn_id":        m["espn_id"],
                    "espn_athlete_id": m["espn_id"],
                }
                for m in matched
            ])
            stmt = stmt.on_conflict_do_update(
                index_elements=["player_id"],
                set_={"name": stmt.excluded.name, "nfl_team": stmt.excluded.nfl_team},
            )
            await db.execute(stmt)
            await db.commit()

        return {"players": matched, "total": len(matched), "query": q, "source": "sleeper_cache"}

    # --- Fallback: local DB (only rostered players) ---
    result = await db.execute(
        select(Player)
        .where(Player.name.ilike(f"%{q}%"))
        .order_by(Player.name)
        .limit(limit)
    )
    db_players = result.scalars().all()
    return {
        "players": [
            {"player_id": p.player_id, "name": p.name, "position": p.position, "nfl_team": p.nfl_team}
            for p in db_players
        ],
        "total": len(db_players),
        "query": q,
        "source": "db_fallback",
    }


@router.post("/tracker/star/{player_id}")
async def star_player(
    player_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Star a player. Triggers the 4-pass Gemini stock analysis in the background.
    The profile may take 15-30 seconds to generate — poll GET /api/tracker/{player_id}
    and check profile_ready=true.
    """
    result = await tracker_service.star_player(user.id, player_id, db)
    await db.commit()

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("detail"))

    return result


@router.delete("/tracker/star/{player_id}")
async def unstar_player(
    player_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unstar a player (soft delete — stock profile is retained)."""
    result = await tracker_service.unstar_player(user.id, player_id, db)
    await db.commit()

    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Player not starred")

    return result


@router.get("/tracker")
async def get_tracker(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all starred players for this user with their stock profiles.
    Sorted by combined_score DESC (highest concern first).
    Players with profile_ready=false have been starred but analysis hasn't completed yet.
    """
    players = await tracker_service.get_tracked_players(user.id, db)
    return {
        "tracked_players": players,
        "total": len(players),
        "user_id": user.id,
    }


@router.get("/tracker/{player_id}")
async def get_tracker_player(
    player_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns full detail for a single tracked player, including historical stats
    by season and the full ADP trend history.
    """
    detail = await tracker_service.get_tracked_player_detail(user.id, player_id, db)
    if not detail:
        raise HTTPException(status_code=404, detail="Player not found in tracker")
    return detail


@router.post("/tracker/refresh/{player_id}")
async def refresh_tracker_player(
    player_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually re-run the 4-pass Gemini analysis for a starred player.
    Use sparingly — each call consumes 4 Gemini API requests.
    """
    success = await tracker_service.refresh_profile(user.id, player_id, db, reason="manual")
    await db.commit()

    if not success:
        raise HTTPException(status_code=404, detail="Player not found in tracker")

    return {"status": "refresh_triggered", "player_id": player_id}
