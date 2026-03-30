"""
Projection orchestration service.

- normalize_name: Cross-source player name matching.
- get_nfl_state: Current week + season type from Sleeper.
- sync_projections: Fetch Sleeper + ESPN projections, compute weighted average, store in DB.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from config import DEFAULT_WEIGHTS
from models.projection import Projection
from services import espn_service, sleeper_service

logger = logging.getLogger(__name__)

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Cache for NFL state — avoids hitting Sleeper on every roster request
_nfl_state_cache: dict = {}


def normalize_name(name: str) -> str:
    """
    Normalize a player name for cross-source matching.
    Lowercases, removes punctuation, strips name suffixes.
    Examples:
      "Ja'Marr Chase"   → "jamarr chase"
      "Calvin Ridley Jr." → "calvin ridley"
      "O'Dell Beckham"  → "odell beckham"
      "Mark Andrews II" → "mark andrews"
    """
    name = name.lower().strip()
    name = re.sub(r"['\.\-]", "", name)       # strip apostrophes, dots, hyphens
    name = re.sub(r"\s+", " ", name)           # collapse whitespace
    parts = [p for p in name.split() if p not in SUFFIXES]
    return " ".join(parts)


async def get_nfl_state() -> dict:
    """
    Returns current NFL state from Sleeper: {week, season, season_type}.
    season_type values: "pre", "regular", "post", "off"
    Cached for 1 hour — avoids a live API call on every roster request.
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
    espn_id_map: dict[str, str],   # sleeper player_id → espn_id
    season: int,
    week: int,
    db: AsyncSession,
) -> dict[str, dict]:
    """
    Fetches Sleeper + ESPN projections concurrently for the given players,
    computes weighted average (redistributing weight if a source is missing),
    deletes stale rows and inserts fresh ones into the projections table.

    Returns {player_id: {sleeper_proj, espn_proj, weighted_proj, confidence_flag}}.
    Returns empty dict during offseason (no projection data available).
    """
    # Fetch both sources concurrently
    sleeper_raw, espn_raw = await asyncio.gather(
        sleeper_service.get_projections(season, week),
        espn_service.get_espn_projections(season, week),
    )

    w_sleeper = DEFAULT_WEIGHTS["sleeper"]   # 0.35
    w_espn = DEFAULT_WEIGHTS["espn"]         # 0.30
    # fp weight (0.35) added in Phase 3

    rows_to_insert = []
    result: dict[str, dict] = {}

    for pid in player_ids:
        sleeper_pts = _extract_sleeper_pts(sleeper_raw.get(pid))
        espn_pts = espn_raw.get(espn_id_map.get(pid, ""))

        sources: dict[str, float] = {}
        if sleeper_pts is not None:
            sources["sleeper"] = w_sleeper
        if espn_pts is not None:
            sources["espn"] = w_espn

        weighted_proj = None
        sources_used = None
        confidence_flag = None

        if sources:
            # Redistribute weight proportionally among available sources
            total = sum(sources.values())
            normalized = {k: round(v / total, 4) for k, v in sources.items()}

            weighted_proj = 0.0
            if sleeper_pts is not None:
                weighted_proj += sleeper_pts * normalized.get("sleeper", 0)
            if espn_pts is not None:
                weighted_proj += espn_pts * normalized.get("espn", 0)
            weighted_proj = round(weighted_proj, 2)

            sources_used = normalized
            confidence_flag = {3: "HIGH", 2: "MEDIUM", 1: "LOW"}.get(len(sources), "LOW")

        row = {
            "player_id": pid,
            "week": week,
            "season": season,
            "sleeper_proj": sleeper_pts,
            "espn_proj": espn_pts,
            "fp_proj": None,           # Phase 3
            "weighted_proj": weighted_proj,
            "sources_used": sources_used,
            "confidence_flag": confidence_flag,
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
