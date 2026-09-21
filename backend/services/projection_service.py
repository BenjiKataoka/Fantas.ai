"""
Projection orchestration service.

- normalize_name: Cross-source player name matching.
- get_nfl_state: Current week + season type from Sleeper.
- sync_projections: Fetch Sleeper + ESPN projections, compute weighted average, store in DB.
"""
import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.projection import Projection
from services import espn_service, fp_service, sleeper_service
from services.projection_engine import compute_weighted_projection
from services.utils import normalize_name  # re-exported for external use

logger = logging.getLogger(__name__)

# Cache for NFL state, avoids hitting Sleeper on every roster request
_nfl_state_cache: dict = {}



async def get_nfl_state() -> dict:
    """
    Returns current NFL state from Sleeper: {week, season, season_type}.
    season_type values: "pre", "regular", "post", "off"
    Cached for 1 hour, avoids a live API call on every roster request.
    Defaults to {week: 1, season: 2025, season_type: "off"} if unavailable.

    """
    cached = _nfl_state_cache.get("state")
    if cached and datetime.utcnow() < cached["expires"]:
        return cached["data"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.sleeper.app/v1/state/nfl")
            resp.raise_for_status()
            state = resp.json()
            data = {
                "week": max(1, min(18, int(state.get("week", 1)))),
                "season": int(state.get("season", 2025)),
                "season_type": state.get("season_type", "off"),
            }
    except Exception as e:
        logger.warning(f"[Projection] Could not fetch NFL state from Sleeper: {e}")
        data = {"week": 1, "season": 2025, "season_type": "off"}

    _nfl_state_cache["state"] = {"data": data, "expires": datetime.utcnow() + timedelta(hours=1)}
    return data


async def sync_projections(
    player_ids: list[str],
    espn_id_map: dict[str, str],       # player_id → espn_id
    name_map: dict[str, str],          # player_id → normalized_name (for FP matching)
    season: int,
    week: int,
    db: AsyncSession,
    weights: dict[str, float] | None = None,  # per-user weights; defaults to DEFAULT_WEIGHTS
) -> dict[str, dict]:
    """
    Fetches Sleeper + ESPN + FantasyPros projections concurrently for the given players,
    computes weighted average via projection_engine (redistributing weight if a source is missing),
    deletes stale rows and inserts fresh ones into the projections table.

    Returns {player_id: {sleeper_proj, espn_proj, fp_proj, weighted_proj, confidence_flag}}.
    All projection values will be None during the offseason.
    """
    # Fetch all three sources concurrently. ESPN returns both id- and name-keyed maps.
    sleeper_raw, espn_pair, fp_raw = await asyncio.gather(
        sleeper_service.get_projections(season, week),
        espn_service.get_espn_projections_full(season, week),
        fp_service.get_fp_projections(week),
    )
    espn_by_id, espn_by_name = espn_pair

    rows_to_insert = []
    result: dict[str, dict] = {}

    for pid in player_ids:
        sleeper_pts = _extract_sleeper_pts(sleeper_raw.get(pid))
        # Match ESPN by espn_id first; fall back to normalized name when Sleeper
        # has no espn_id for this player (otherwise ESPN would be dropped for them).
        espn_pts = espn_by_id.get(espn_id_map.get(pid, ""))
        if espn_pts is None:
            espn_pts = espn_by_name.get(name_map.get(pid, ""))
        fp_pts = fp_raw.get(name_map.get(pid, ""))

        computed = compute_weighted_projection(sleeper_pts, espn_pts, fp_pts, weights)

        row = {
            "player_id": pid,
            "week": week,
            "season": season,
            "sleeper_proj": sleeper_pts,
            "espn_proj": espn_pts,
            "fp_proj": fp_pts,
            "weighted_proj": computed["weighted_proj"],
            "sources_used": computed["sources_used"],
            "confidence_flag": computed["confidence_flag"],
        }
        rows_to_insert.append(row)
        result[pid] = row

    if rows_to_insert:
        # Delete stale rows for this week/season before inserting fresh data
        await db.execute(
            delete(Projection).where(
                Projection.player_id.in_(player_ids),
                Projection.week == week,
                Projection.season == season,
            )
        )
        for row in rows_to_insert:
            db.add(Projection(**row))
        # Caller (roster.py) commits after this returns

    logger.info(
        f"[Projection] Synced {len(rows_to_insert)} projections "
        f"for season={season} week={week}"
    )
    return result


def _extract_sleeper_pts(raw: dict | None) -> float | None:
    """Pull PPR points from a Sleeper projection dict. Returns None if unavailable."""
    if not raw:
        return None
    pts = raw.get("pts_ppr") or raw.get("pts_half_ppr") or raw.get("pts_std")
    if pts is None:
        return None
    return round(float(pts), 2)
