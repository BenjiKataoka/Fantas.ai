"""
Projections router, on-demand weekly projections for the user's roster.

GET /api/projections/{week}
  Fetches fresh projections for the user's rostered players for the given week,
  using the user's saved weights from the users table.
  Does not re-sync the full roster, reads player list from my_roster.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.player import Player
from models.roster import MyRoster
from services.league_service import resolve_user_league
from models.user import User
from auth import get_current_user
from services.projection_engine import compute_weighted_projection, weights_from_user
from services.projection_service import get_nfl_state
from services import espn_service, fp_service, sleeper_service
from services.utils import extract_sleeper_pts, normalize_name

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/projections/{week}")
async def get_projections(
    week: int,
    league_id: str | None = Query(None, description="League to use; defaults to the last one loaded"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns projections for all of the user's rostered players for a given week.
    Uses the user's saved projection weights (falls back to defaults if not set).
    Fetches fresh data from all 3 sources, does not read from the projections table.
    """
    if week < 1 or week > 18:
        raise HTTPException(status_code=400, detail="Week must be between 1 and 18.")

    nfl_state = await get_nfl_state()
    season = nfl_state["season"]

    # Load user weights
    weights = weights_from_user(user)

    # Load rostered player IDs + player details
    ul = await resolve_user_league(db, user.id, league_id)
    result = await db.execute(
        select(MyRoster, Player)
        .join(Player, MyRoster.player_id == Player.player_id)
        .where(MyRoster.user_league_id == (ul.id if ul else -1))
    )
    rows = result.all()

    if not rows:
        return {
            "projections": [],
            "week": week,
            "season": season,
            "season_type": nfl_state["season_type"],
            "weights_used": weights,
            "warning": "No roster found. Call /api/roster first.",
        }

    player_ids = [roster.player_id for roster, _ in rows]
    espn_id_map = {
        roster.player_id: player.espn_id
        for roster, player in rows
        if player.espn_id
    }
    name_map = {
        roster.player_id: normalize_name(player.name)
        for roster, player in rows
    }

    # Fetch all 3 sources concurrently
    import asyncio
    sleeper_raw, espn_raw, fp_raw = await asyncio.gather(
        sleeper_service.get_projections(season, week),
        espn_service.get_espn_projections(season, week),
        fp_service.get_fp_projections(week),
    )

    projections_out = []
    for roster, player in rows:
        pid = player.player_id
        sleeper_pts = extract_sleeper_pts(sleeper_raw.get(pid))
        espn_pts = espn_raw.get(espn_id_map.get(pid, ""))
        fp_pts = fp_raw.get(name_map.get(pid, ""))

        computed = compute_weighted_projection(sleeper_pts, espn_pts, fp_pts, weights)

        projections_out.append({
            "player_id": pid,
            "name": player.name,
            "position": player.position,
            "nfl_team": player.nfl_team,
            "is_starter": roster.is_starter,
            "sleeper_proj": sleeper_pts,
            "espn_proj": espn_pts,
            "fp_proj": fp_pts,
            "weighted_proj": computed["weighted_proj"],
            "sources_used": computed["sources_used"],
            "confidence_flag": computed["confidence_flag"],
        })

    # Sort starters first, then by position
    position_order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "DEF": 5}
    projections_out.sort(
        key=lambda x: (0 if x["is_starter"] else 1, position_order.get(x["position"], 9))
    )

    logger.info(
        f"[Projections] Fetched week {week} projections for {len(projections_out)} players "
        f"(season={season}, weights={weights})"
    )

    return {
        "projections": projections_out,
        "week": week,
        "season": season,
        "season_type": nfl_state["season_type"],
        "weights_used": weights,
    }
