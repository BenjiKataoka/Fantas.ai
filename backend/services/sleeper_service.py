import httpx
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

SLEEPER_BASE = "https://api.sleeper.app/v1"
# Stats/projections live on a different host and return a LIST with populated stats;
# the app/v1 projections endpoint returns player shells with empty stats.
SLEEPER_STATS_BASE = "https://api.sleeper.com"
CURRENT_SEASON = 2025

# Simple in-memory cache: { cache_key: (data, expires_at) }
_cache: dict = {}
CACHE_TTL_HOURS = 6


def _get_cache(key: str):
    entry = _cache.get(key)
    if entry and datetime.utcnow() < entry[1]:
        return entry[0]
    return None


def _set_cache(key: str, data, ttl_hours: int = CACHE_TTL_HOURS):
    _cache[key] = (data, datetime.utcnow() + timedelta(hours=ttl_hours))


async def get_user_id(username: str) -> Optional[str]:
    cache_key = f"sleeper_user_{username}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{SLEEPER_BASE}/user/{username}", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            user_id = data.get("user_id")
            if user_id:
                _set_cache(cache_key, user_id, ttl_hours=24)
            return user_id
    except Exception as e:
        logger.error(f"[Sleeper] get_user_id failed for {username}: {e}")
        return None


async def get_leagues(user_id: str, season: int = CURRENT_SEASON) -> list:
    cache_key = f"sleeper_leagues_{user_id}_{season}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SLEEPER_BASE}/user/{user_id}/leagues/nfl/{season}", timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            _set_cache(cache_key, data, ttl_hours=6)
            return data
    except Exception as e:
        logger.error(f"[Sleeper] get_leagues failed for user {user_id}: {e}")
        return []


async def get_eligible_leagues(user_id: str, season: int = CURRENT_SEASON) -> list:
    """Returns only redraft PPR leagues, filters out dynasty, keeper, and non-PPR."""
    all_leagues = await get_leagues(user_id, season)
    eligible = []
    for league in all_leagues:
        is_redraft = league.get("settings", {}).get("type") == 0
        is_ppr = league.get("scoring_settings", {}).get("rec") == 1.0
        if is_redraft and is_ppr:
            eligible.append({
                "league_id": league.get("league_id"),
                "name": league.get("name"),
                "total_rosters": league.get("total_rosters"),
                "season": league.get("season"),
            })
    return eligible


async def get_league_rosters(league_id: str, force: bool = False) -> list:
    """Every roster in a league. Cached 15 min since waiver claims change ownership;
    force skips the cache (manual refresh right after a roster move)."""
    cache_key = f"sleeper_rosters_{league_id}"
    cached = None if force else _get_cache(cache_key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{SLEEPER_BASE}/league/{league_id}/rosters", timeout=10)
            resp.raise_for_status()
            data = resp.json() or []
            _set_cache(cache_key, data, ttl_hours=0.25)
            return data
    except Exception as e:
        logger.error(f"[Sleeper] get_league_rosters failed for league {league_id}: {e}")
        return []


async def get_roster(league_id: str, user_id: str, force: bool = False) -> Optional[dict]:
    """Returns the roster belonging to user_id in the given league."""
    rosters = await get_league_rosters(league_id, force=force)
    return next((r for r in rosters if r.get("owner_id") == user_id), None)


async def get_league(league_id: str) -> Optional[dict]:
    """League object (settings, scoring, roster_positions). Cached 6h."""
    cache_key = f"sleeper_league_{league_id}"
    cached = _get_cache(cache_key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{SLEEPER_BASE}/league/{league_id}", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            _set_cache(cache_key, data)
            return data
    except Exception as e:
        logger.error(f"[Sleeper] get_league failed for {league_id}: {e}")
        return None


async def get_matchups(league_id: str, week: int, live: bool = False) -> list:
    """Every roster's matchup for a week: starters, players, and players_points in
    the league's own scoring. Live weeks cache 10 minutes, finished weeks 24h."""
    cache_key = f"sleeper_matchups_{league_id}_{week}"
    cached = _get_cache(cache_key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{SLEEPER_BASE}/league/{league_id}/matchups/{week}", timeout=10)
            resp.raise_for_status()
            data = resp.json() or []
            _set_cache(cache_key, data, ttl_hours=(1 / 6) if live else 24)
            return data
    except Exception as e:
        logger.error(f"[Sleeper] get_matchups failed for league {league_id} week {week}: {e}")
        return []


async def get_all_players() -> dict:
    """Returns Sleeper's full NFL player map. Heavy call, cache for 24h."""
    cache_key = "sleeper_all_players"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{SLEEPER_BASE}/players/nfl")
            resp.raise_for_status()
            data = resp.json()
            _set_cache(cache_key, data, ttl_hours=24)
            return data
    except Exception as e:
        logger.error(f"[Sleeper] get_all_players failed: {e}")
        return {}


async def get_projections(season: int, week: int) -> dict:
    """
    Returns Sleeper projections keyed by player_id: {player_id: stats_dict}.

    Uses api.sleeper.com (not api.sleeper.app/v1), the app host returns player shells
    with empty stats. The stats host returns a LIST of {player_id, stats, ...} which we
    reshape into a dict so callers can look up by player_id.
    """
    cache_key = f"sleeper_projections_{season}_{week}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{SLEEPER_STATS_BASE}/projections/nfl/{season}/{week}",
                params={
                    "season_type": "regular",
                    "position[]": ["QB", "RB", "WR", "TE", "K"],
                    "order_by": "pts_ppr",
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            resp.raise_for_status()
            raw = resp.json()
            # Reshape list → {player_id: stats}. Tolerate an unexpected dict response.
            if isinstance(raw, list):
                data = {
                    str(item["player_id"]): (item.get("stats") or {})
                    for item in raw
                    if item.get("player_id") is not None
                }
            else:
                data = raw
            _set_cache(cache_key, data, ttl_hours=6)
            return data
    except Exception as e:
        logger.error(f"[Sleeper] get_projections failed for week {week}: {e}")
        return {}


async def get_trending_players(trend_type: str = "add", limit: int = 25) -> list:
    """trend_type: 'add' or 'drop'"""
    cache_key = f"sleeper_trending_{trend_type}_{limit}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SLEEPER_BASE}/players/nfl/trending/{trend_type}",
                params={"limit": limit},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            _set_cache(cache_key, data, ttl_hours=1)
            return data
    except Exception as e:
        logger.error(f"[Sleeper] get_trending failed ({trend_type}): {e}")
        return []


async def get_league_users(league_id: str) -> list:
    """League members (display_name, metadata.team_name). Cached 6h."""
    cache_key = f"sleeper_users_{league_id}"
    cached = _get_cache(cache_key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{SLEEPER_BASE}/league/{league_id}/users", timeout=10)
            resp.raise_for_status()
            data = resp.json() or []
            _set_cache(cache_key, data)
            return data
    except Exception as e:
        logger.error(f"[Sleeper] get_league_users failed for {league_id}: {e}")
        return []
