"""
ESPN Fantasy API integration via direct httpx calls (no espn-api library).

- get_espn_projections: Public endpoint, no auth required.
- get_espn_roster: Authenticated roster sync, requires ESPN_S2 + SWID cookies.
"""
import json
import logging
from datetime import datetime, timedelta

import httpx

from services.utils import normalize_name

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


# ESPN stat entry discriminators (in player.stats[])
_ESPN_STAT_PROJECTED = 1   # statSourceId: 1=projected, 0=actual
_ESPN_SPLIT_WEEKLY = 1     # statSplitTypeId: 1=single week, 0=season total


def _extract_espn_proj(player: dict, season: int, week: int) -> float | None:
    """
    Pulls the projected weekly fantasy points for a player from ESPN's stats array.

    Each player carries dozens of stat entries; the projection for a given week is the
    one with statSourceId=1 (projected), statSplitTypeId=1 (weekly), and matching
    scoringPeriodId/seasonId. appliedTotal is already scored under the league format
    (leaguedefaults/3 = PPR). Returns None if no projection exists yet for that week.
    """
    for s in player.get("stats", []):
        if (
            s.get("statSourceId") == _ESPN_STAT_PROJECTED
            and s.get("statSplitTypeId") == _ESPN_SPLIT_WEEKLY
            and s.get("scoringPeriodId") == week
            and s.get("seasonId") == season
        ):
            pts = s.get("appliedTotal")
            return round(float(pts), 2) if pts is not None else None
    return None


async def get_espn_projections_full(
    season: int, week: int
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Fetches ESPN public projected fantasy points for all skill-position players.
    No authentication required. Single fetch, cached, returns TWO views:
      (by_espn_id, by_normalized_name)

    The name map is a fallback for players whose Sleeper record has no espn_id
    (Sleeper returns None for some players, which would otherwise drop ESPN entirely
    for them). Callers match on espn_id first, then fall back to normalized name.

    Sorted by PPR draft rank so the returned pool is the fantasy-relevant players
    (an unplayed week has no applied totals to sort on). Projections are read from
    each player's stats array, see _extract_espn_proj.
    """
    cache_key = f"espn_proj_{season}_{week}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    filter_header = json.dumps({
        "players": {
            "limit": 500,
            "filterSlotIds": {"value": [0, 2, 4, 6, 17]},  # QB/RB/WR/TE/K
            "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "PPR"},
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
        return {}, {}

    by_id: dict[str, float] = {}
    by_name: dict[str, float] = {}
    for entry in data.get("players", []):
        # The player object is at entry["player"] (entry itself IS the player pool entry)
        player = entry.get("player", {})
        espn_id = str(player.get("id", ""))
        pts = _extract_espn_proj(player, season, week)
        if pts is None or pts <= 0:
            continue
        if espn_id:
            by_id[espn_id] = pts
        full_name = player.get("fullName")
        if full_name:
            by_name[normalize_name(full_name)] = pts

    if not by_id:
        logger.warning(
            f"[ESPN] No projections returned for season={season} week={week}. "
            "Source may not have posted projections for this week yet."
        )

    result = (by_id, by_name)
    _set_cache(cache_key, result, ttl_hours=6)
    logger.info(f"[ESPN] Loaded {len(by_id)} projections for week {week}")
    return result


async def get_espn_market_pool(season: int, week: int) -> dict[str, dict]:
    """
    One ESPN pull → an in-season market snapshot per player, keyed by normalized name:
      { norm_name: {espn_id, position, position_rank, overall_rank, adp, percent_rostered} }

    In-season, ADP is frozen, so the meaningful "rank" is derived from ESPN's WEEKLY
    projected points (higher points = better rank), grouped by position, this moves as
    projections update. ADP and % rostered come from each player's ownership block.
    Players with no projection this week (bye/inactive) keep null ranks but still carry
    ADP / % rostered. Cached 6h.
    """
    cache_key = f"espn_market_{season}_{week}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    filter_header = json.dumps({
        "players": {
            "limit": 500,
            "filterSlotIds": {"value": [0, 2, 4, 6, 17]},  # QB/RB/WR/TE/K
            "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "PPR"},
        }
    })
    url = f"{ESPN_BASE}/seasons/{season}/segments/0/leaguedefaults/3"
    headers = {"X-Fantasy-Filter": filter_header, "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=headers, params={"view": "kona_player_info"})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"[ESPN] get_espn_market_pool failed season={season} week={week}: {e}")
        return {}

    rows = []
    for entry in data.get("players", []):
        pl = entry.get("player", {})
        pos = _espn_position(pl.get("defaultPositionId"))
        if pos not in ("QB", "RB", "WR", "TE", "K") or not pl.get("fullName"):
            continue
        own = pl.get("ownership") or {}
        rows.append({
            "name": pl.get("fullName"),
            "espn_id": str(pl.get("id", "")),
            "position": pos,
            "proj": _extract_espn_proj(pl, season, week),
            "adp": own.get("averageDraftPosition"),
            "percent_rostered": own.get("percentOwned"),
        })

    # Rank the projectable players (proj desc) → overall + within-position rank.
    ranked = sorted((r for r in rows if r["proj"] is not None), key=lambda r: r["proj"], reverse=True)
    pos_counter: dict[str, int] = {}
    for i, r in enumerate(ranked, 1):
        r["overall_rank"] = i
        pos_counter[r["position"]] = pos_counter.get(r["position"], 0) + 1
        r["position_rank"] = pos_counter[r["position"]]

    pool: dict[str, dict] = {}
    for r in rows:
        pool[normalize_name(r["name"])] = {
            "espn_id": r["espn_id"],
            "position": r["position"],
            "position_rank": r.get("position_rank"),
            "overall_rank": r.get("overall_rank"),
            "adp": round(r["adp"], 1) if r.get("adp") is not None else None,
            "percent_rostered": round(r["percent_rostered"], 1) if r.get("percent_rostered") is not None else None,
        }

    _set_cache(cache_key, pool, ttl_hours=6)
    logger.info(f"[ESPN] market pool: {len(pool)} players, {len(ranked)} ranked by projection (week {week})")
    return pool


async def get_espn_projections(season: int, week: int) -> dict[str, float]:
    """Backward-compatible id-keyed view: {espn_player_id_str: projected_points}."""
    by_id, _ = await get_espn_projections_full(season, week)
    return by_id


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
                logger.error("[ESPN] get_espn_roster: 401, ESPN cookies expired or invalid")
                return []
            if resp.status_code == 404:
                logger.error(f"[ESPN] get_espn_roster: 404, league {league_id} not found for season {season}")
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


# ── Multi-league: ESPN leagues as a second platform ───────────────────────────
# ESPN lineup slot id → the Sleeper slot names the rest of the app uses (lineup solver,
# SLOT_ELIGIBLE, frontend labels). Bench (20) and IR (21) aren't lineup slots.
ESPN_TO_SLOT = {
    0: "QB", 2: "RB", 3: "WRRB_FLEX", 4: "WR", 5: "REC_FLEX", 6: "TE",
    7: "SUPER_FLEX", 16: "DEF", 17: "K", 23: "FLEX",
}
FAN_API = "https://fan.api.espn.com/apis/v2/fans/{swid}"


def _cookie_headers(espn_s2: str | None, swid: str | None) -> dict:
    """Public leagues need no cookies; private ones need both."""
    headers = {"Accept": "application/json"}
    if espn_s2 and swid:
        headers["Cookie"] = f"espn_s2={espn_s2}; SWID={swid}"
    return headers


class EspnAuthError(Exception):
    """ESPN rejected the cookies (expired or wrong account)."""


async def get_espn_fan_leagues(espn_s2: str, swid: str, season: int) -> list[dict]:
    """Every ESPN football league this account is in for a season, from ESPN's (unofficial)
    fan profile endpoint: [{league_id, name}]. Raises EspnAuthError on bad cookies."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(FAN_API.format(swid=swid), headers=_cookie_headers(espn_s2, swid),
                                    params={"displayHiddenPrefs": "true"})
    except Exception as e:
        logger.error(f"[ESPN] fan leagues request failed: {e}")
        return []
    # An unknown SWID comes back 404, not 401, so treat it as bad cookies too.
    if resp.status_code in (401, 403, 404):
        raise EspnAuthError("ESPN cookies were rejected")
    if resp.status_code != 200:
        logger.error(f"[ESPN] fan leagues status {resp.status_code}")
        return []
    leagues = []
    for pref in resp.json().get("preferences", []):
        entry = (pref.get("metaData") or {}).get("entry") or {}
        group = (entry.get("groups") or [{}])[0]
        if entry.get("abbrev") == "FFL" and entry.get("seasonId") == season and group.get("groupId"):
            leagues.append({"league_id": str(group["groupId"]), "name": group.get("groupName")})
    return leagues


async def get_espn_league(league_id: str, season: int, espn_s2: str | None = None,
                          swid: str | None = None, force: bool = False) -> dict | None:
    """League settings plus every team's roster in one call. Cached 15 minutes, like the
    Sleeper rosters, since waiver claims change ownership. Cookies are optional for public
    leagues. Raises EspnAuthError on 401 (bad cookies, or a private league without them)."""
    cache_key = f"espn_league_{league_id}_{season}"
    cached = None if force else _get_cache(cache_key)
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{ESPN_BASE}/seasons/{season}/segments/0/leagues/{league_id}",
                headers=_cookie_headers(espn_s2, swid),
                params=[("view", "mSettings"), ("view", "mTeam"), ("view", "mRoster")],
            )
    except Exception as e:
        logger.error(f"[ESPN] get_espn_league failed for {league_id}: {e}")
        return None
    if resp.status_code == 401:
        raise EspnAuthError("ESPN cookies were rejected")
    if resp.status_code != 200:
        logger.error(f"[ESPN] get_espn_league {league_id} status {resp.status_code}")
        return None
    data = resp.json()
    _set_cache(cache_key, data, ttl_hours=0.25)
    return data


def espn_roster_positions(league: dict) -> list[str]:
    """The league's lineup as Sleeper-style slot names, e.g. ["QB", "RB", "RB", ..., "FLEX"]."""
    counts = ((league.get("settings") or {}).get("rosterSettings") or {}).get("lineupSlotCounts") or {}
    return [ESPN_TO_SLOT[int(k)] for k, n in counts.items() if int(k) in ESPN_TO_SLOT for _ in range(n)]


def espn_is_redraft_ppr(league: dict) -> bool:
    """Same rule as Sleeper's filter: 1 point per reception and no keepers."""
    st = league.get("settings") or {}
    rec = next((i.get("points") for i in (st.get("scoringSettings") or {}).get("scoringItems") or []
                if i.get("statId") == 53), None)
    return rec == 1.0 and not (st.get("draftSettings") or {}).get("keeperCount")


def espn_my_team(league: dict, swid: str | None = None, team_id: int | None = None) -> dict | None:
    """The user's team: by the team they picked (public leagues), else by SWID ownership."""
    teams = league.get("teams") or []
    if team_id is not None:
        return next((t for t in teams if t.get("id") == team_id), None)
    if not swid:
        return None
    swid_clean = swid.strip("{} ").lower()
    return next((t for t in teams
                 if any(o.strip("{} ").lower() == swid_clean for o in t.get("owners") or [])), None)


def espn_teams(league: dict) -> list[dict]:
    """Team picker for public leagues: [{team_id, name, owner}]."""
    members = {m.get("id"): m.get("displayName") for m in league.get("members") or []}
    return [{"team_id": t.get("id"), "name": t.get("name") or t.get("abbrev") or f"Team {t.get('id')}",
             "owner": members.get(t.get("primaryOwner"))}
            for t in league.get("teams") or []]


def parse_espn_league_id(text: str) -> str | None:
    """A pasted league link (…/league?leagueId=123) or a bare id → "123"."""
    import re
    m = re.search(r"leagueId=(\d+)", text) or re.fullmatch(r"\s*(\d{4,})\s*", text)
    return m.group(1) if m else None


def espn_to_sleeper_ids(entries: list[dict], all_players: dict) -> list[tuple[str, dict]]:
    """Map ESPN roster entries onto Sleeper player ids (the app's canonical key): by the
    espn_id Sleeper stores, then by normalized name + position for the few it leaves blank.
    Returns [(sleeper_id, entry)], dropping players that can't be matched (team defenses)."""
    by_espn = {str(p["espn_id"]): pid for pid, p in all_players.items() if p.get("espn_id") is not None}
    by_name = {(normalize_name(p.get("full_name") or ""), p.get("position")): pid
               for pid, p in all_players.items() if p.get("full_name")}
    out = []
    for e in entries:
        pl = (e.get("playerPoolEntry") or {}).get("player") or {}
        pid = by_espn.get(str(pl.get("id"))) or by_name.get(
            (normalize_name(pl.get("fullName") or ""), _espn_position(pl.get("defaultPositionId"))))
        if pid:
            out.append((pid, e))
        else:
            logger.info(f"[ESPN] no Sleeper match for {pl.get('fullName')} ({pl.get('id')})")
    return out
