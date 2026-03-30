"""
ESPN Fantasy API integration via direct httpx calls (no espn-api library).

- get_espn_projections: Public endpoint — no auth required.
- get_espn_roster: Authenticated roster sync — requires ESPN_S2 + SWID cookies.
"""
import json
import logging
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

ESPN_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

# ESPN lineup slot IDs → position labels
ESPN_SLOT_MAP = {
    0: "QB", 2: "RB", 4: "WR", 6: "TE",
    17: "K", 16: "DST", 20: "BN", 21: "IR", 23: "FLEX",
}

# In-memory cache: {key: (data, expires_at)}
_cache: dict = {}


def _get_cache(key: str):
    entry = _cache.get(key)
    if entry and datetime.utcnow() < entry[1]:
        return entry[0]
    return None


def _set_cache(key: str, data, ttl_hours: int = 6):
    _cache[key] = (data, datetime.utcnow() + timedelta(hours=ttl_hours))


async def get_espn_projections(season: int, week: int) -> dict[str, float]:
    """
    Fetches ESPN public projected fantasy points for all skill-position players.
    No authentication required.
    Returns {espn_player_id_str: projected_points}.

    ESPN stat period format: "00{season}{week:02d}" (e.g. "00202501" = 2025 Week 1).
    During the offseason ESPN returns no projected values — empty dict is expected.
    """
    cache_key = f"espn_proj_{season}_{week}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    stat_period = f"00{season}{week:02d}"
    filter_header = json.dumps({
        "players": {
            "limit": 1000,
            "filterSlotIds": {"value": [0, 2, 4, 6, 17, 16]},
            "sortAppliedStatTotal": {
                "sortAsc": False,
                "sortPriority": 3,
                "value": stat_period,
            },
        }
    })

    url = f"{ESPN_BASE}/seasons/{season}/segments/0/leaguedefaults/3"
    headers = {
        "X-Fantasy-Filter": filter_header,
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=headers, params={"view": "kona_player_info"})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"[ESPN] get_espn_projections failed season={season} week={week}: {e}")
        return {}

    projections: dict[str, float] = {}
    for entry in data.get("players", []):
        pool = entry.get("playerPoolEntry", {})
        player = pool.get("player", {})
        espn_id = str(player.get("id", ""))
        pts = pool.get("appliedStatTotal") or 0.0
        if espn_id and float(pts) > 0:
            projections[espn_id] = round(float(pts), 2)

    if not projections:
        logger.warning(
            f"[ESPN] No projections returned for season={season} week={week} "
            f"(stat_period={stat_period}). Expected during offseason."
        )

    _set_cache(cache_key, projections, ttl_hours=6)
    logger.info(f"[ESPN] Loaded {len(projections)} projections for week {week}")
    return projections


async def get_espn_roster(
    league_id: int,
    espn_s2: str,
    swid: str,
    season: int,
) -> list[dict]:
    """
    Fetches the authenticated user's team roster from ESPN.
    Identifies the user's team by matching SWID to team owner.
    Returns list of {espn_player_id, name, position, is_starter, slot}.
    """
    cache_key = f"espn_roster_{league_id}_{season}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    url = f"{ESPN_BASE}/seasons/{season}/segments/0/leagues/{league_id}"
    headers = {
        "Cookie": f"espn_s2={espn_s2}; SWID={swid}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                url,
                headers=headers,
                params={"view": ["mTeam", "mRoster"]},
            )
            if resp.status_code == 401:
                logger.error("[ESPN] get_espn_roster: 401 — ESPN cookies expired or invalid")
                return []
            if resp.status_code == 404:
                logger.error(f"[ESPN] get_espn_roster: 404 — league {league_id} not found for season {season}")
                return []
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"[ESPN] get_espn_roster failed for league {league_id}: {e}")
        return []

    # Find the team owned by this user via SWID match
    swid_clean = swid.strip("{} ").lower()
    my_team = None
    for team in data.get("teams", []):
        for owner_id in team.get("owners", []):
            if owner_id.strip("{} ").lower() == swid_clean:
                my_team = team
                break
        if my_team:
            break

    if not my_team:
        logger.warning(
            f"[ESPN] Could not find team for SWID={swid[:8]}... in league {league_id}. "
            "Verify SWID is correct and the account owns a team in this league."
        )
        return []

    roster_out = []
    for entry in my_team.get("roster", {}).get("entries", []):
        slot_id = entry.get("lineupSlotId", 20)
        slot = ESPN_SLOT_MAP.get(slot_id, "BN")
        is_starter = slot not in ("BN", "IR")

        pool = entry.get("playerPoolEntry", {})
        player = pool.get("player", {})
        espn_player_id = str(player.get("id", ""))
        name = player.get("fullName", "")
        position = _espn_position(player.get("defaultPositionId"))

        if espn_player_id:
            roster_out.append({
                "espn_player_id": espn_player_id,
                "name": name,
                "position": position,
                "is_starter": is_starter,
                "slot": slot,
            })

    logger.info(f"[ESPN] Loaded {len(roster_out)} players from ESPN roster for league {league_id}")
    _set_cache(cache_key, roster_out, ttl_hours=6)
    return roster_out


def _espn_position(pos_id: int | None) -> str:
    """Maps ESPN defaultPositionId to position string."""
    return {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}.get(pos_id or 0, "")
