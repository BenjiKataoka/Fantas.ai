import httpx
import logging
from datetime import datetime, timedelta
from typing import Optional
from services.cache_service import TTLCache

logger = logging.getLogger(__name__)

ESPN_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news"
ESPN_INJURIES_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/teams/{team_id}/injuries"
ESPN_TRANSACTIONS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/transactions"
ESPN_ATHLETE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/athletes/{athlete_id}"
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

# ESPN's scoreboard abbreviations that differ from Sleeper's (the app's canonical ones).
ESPN_TO_SLEEPER_TEAM = {"WSH": "WAS"}

_cache = TTLCache(default_ttl_hours=1.0)


async def get_espn_news(limit: int = 50, force_refresh: bool = False) -> list[dict]:
    """
    Fetch NFL news from the public ESPN Sports API.
    Returns list of dicts: {player_name, headline, news_body, published_at, source_url, source, espn_athlete_id}.
    Cache TTL: 1h.
    """
    cache_key = f"espn_news_{limit}"
    if not force_refresh:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(ESPN_NEWS_URL, params={"limit": limit})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"[ESPN News] fetch failed: {e}")
        return []

    items = _parse_espn_news(data)
    _cache.set(cache_key, items, ttl_hours=1.0)
    logger.info(f"[ESPN News] fetched {len(items)} news items")
    return items


def _parse_espn_news(data: dict) -> list[dict]:
    items = []
    for article in data.get("articles", []):
        # Extract linked athlete if present
        player_name = None
        espn_athlete_id = None
        categories = article.get("categories", [])
        for cat in categories:
            if cat.get("type") == "athlete":
                player_name = cat.get("athleteName") or cat.get("description")
                espn_athlete_id = str(cat.get("athleteId", "")) or None
                break

        # Skip non-player news (team/league level)
        if not player_name:
            continue

        headline = article.get("headline", "")
        description = article.get("description", "")
        story = article.get("story", "")
        # Prefer description over story for brevity; story can be very long
        news_body = (description or story or "")[:2000]

        # Timestamp
        published_str = article.get("published", "")
        published_at = _parse_espn_timestamp(published_str)

        # Source URL, use web link if available
        links = article.get("links", {})
        web_href = links.get("web", {}).get("href")
        mobile_href = links.get("mobile", {}).get("href")
        source_url = web_href or mobile_href

        if not headline:
            continue

        items.append({
            "player_name": player_name,
            "headline": headline,
            "news_body": news_body or None,
            "published_at": published_at,
            "source_url": source_url,
            "source": "ESPN",
            "espn_athlete_id": espn_athlete_id,
        })

    return items


def _parse_espn_timestamp(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(ts, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


async def get_espn_injuries(team_id: int, force_refresh: bool = False) -> list[dict]:
    """
    Fetch injury report for a single NFL team from ESPN's sports core API.
    Returns list of dicts: {espn_athlete_id, player_name, status, detail, return_date}.
    Cache TTL: 2h.
    """
    cache_key = f"espn_injuries_{team_id}"
    if not force_refresh:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

    url = ESPN_INJURIES_URL.format(team_id=team_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"[ESPN Injuries] team {team_id} fetch failed: {e}")
        return []

    items = _parse_espn_injuries(data)
    _cache.set(cache_key, items, ttl_hours=2.0)
    return items


def _parse_espn_injuries(data: dict) -> list[dict]:
    items = []
    for injury in data.get("items", []):
        athlete_ref = injury.get("athlete", {})
        # $ref links look like: .../athletes/12345, extract the ID
        athlete_url = athlete_ref.get("$ref", "")
        espn_athlete_id = athlete_url.rstrip("/").split("/")[-1] if athlete_url else None

        status = injury.get("status", "")
        detail = injury.get("details", {})
        player_name = detail.get("fantasyStatus", {}).get("description") or ""

        items.append({
            "espn_athlete_id": espn_athlete_id,
            "player_name": player_name,
            "status": status,
            "injury_type": detail.get("type", ""),
            "injury_location": detail.get("location", ""),
            "detail": detail.get("detail", ""),
            "side": detail.get("side", ""),
            "return_date": detail.get("returnDate"),
        })
    return items


async def get_espn_transactions(limit: int = 50, force_refresh: bool = False) -> list[dict]:
    """
    Fetch recent NFL transactions (signings, cuts, trades) from ESPN.
    Returns list of dicts: {player_name, headline, news_body, published_at, source_url, source}.
    Cache TTL: 2h.
    """
    cache_key = f"espn_transactions_{limit}"
    if not force_refresh:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(ESPN_TRANSACTIONS_URL, params={"limit": limit})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"[ESPN Transactions] fetch failed: {e}")
        return []

    items = _parse_espn_news(data)  # same shape as news articles
    _cache.set(cache_key, items, ttl_hours=2.0)
    logger.info(f"[ESPN Transactions] fetched {len(items)} items")
    return items


async def get_player_injury_status(espn_athlete_id: str) -> Optional[dict]:
    """
    Fetch a single player's current status from ESPN athlete endpoint.
    Returns dict with injury_status and injury_detail, or None on failure.
    Cache TTL: 1h.
    """
    cache_key = f"espn_athlete_{espn_athlete_id}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    url = ESPN_ATHLETE_URL.format(athlete_id=espn_athlete_id)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"[ESPN Athlete] {espn_athlete_id} fetch failed: {e}")
        return None

    injuries = data.get("injuries", [])
    status = "Active"
    detail = None
    if injuries:
        latest = injuries[0]
        status = latest.get("status", "Active")
        detail = latest.get("details", {}).get("detail")

    result = {"injury_status": status, "injury_detail": detail}
    _cache.set(cache_key, result, ttl_hours=1.0)
    return result


async def get_teams_playing_today(force_refresh: bool = False) -> set[str]:
    """
    Returns a set of NFL team abbreviations (e.g. {"KC", "SF", "DAL"}) that
    have a game scheduled today, using the ESPN scoreboard endpoint.
    Cache TTL: 1h, schedule doesn't change during the day.
    Returns empty set if the request fails or no games today.
    """
    from datetime import date
    today_str = date.today().strftime("%Y%m%d")
    cache_key = f"teams_playing_{today_str}"

    if not force_refresh:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                ESPN_SCOREBOARD_URL,
                params={"dates": today_str, "limit": 16},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"[ESPN Scoreboard] get_teams_playing_today failed: {e}")
        return set()

    teams: set[str] = set()
    for event in data.get("events", []):
        for competition in event.get("competitions", []):
            for competitor in competition.get("competitors", []):
                abbrev = competitor.get("team", {}).get("abbreviation")
                if abbrev:
                    teams.add(abbrev.upper())

    _cache.set(cache_key, teams, ttl_hours=1.0)
    logger.info(f"[ESPN Scoreboard] {len(teams)} teams playing today: {sorted(teams)}")
    return teams


async def get_week_schedule(season: int, week: int) -> dict[str, dict]:
    """{team: {"kickoff": aware UTC datetime, "state": "pre"|"in"|"post"}} for one regular
    season week, in Sleeper's team abbreviations. A team missing from the map is on bye.
    Cached 1 hour (game states change on Sundays)."""
    cache_key = f"schedule_{season}_{week}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(ESPN_SCOREBOARD_URL, params={"week": week, "seasontype": 2, "dates": season})
            resp.raise_for_status()
            events = resp.json().get("events", [])
    except Exception as e:
        logger.error(f"[NFL] week schedule failed season={season} week={week}: {e}")
        return {}
    out: dict[str, dict] = {}
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        try:
            kickoff = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        state = ((comp.get("status") or {}).get("type") or {}).get("state", "pre")
        for c in comp.get("competitors", []):
            abbr = (c.get("team") or {}).get("abbreviation")
            if abbr:
                out[ESPN_TO_SLEEPER_TEAM.get(abbr, abbr)] = {"kickoff": kickoff, "state": state}
    # 5 minutes, matching the live score caches: a player's number switches from his
    # projection to real points only once this says his game is under way.
    _cache.set(cache_key, out, ttl_hours=1 / 12)
    return out


async def last_complete_week(season: int, week: int) -> int:
    """The most recent week whose games have all finished, so callers never offer a recap
    of a week that is still being played.

    Sleeper's own week doesn't roll over until the Tuesday after Monday night, so between
    the final whistle and that rollover `week` is complete while Sleeper still calls it
    current. Asking the scoreboard is the only way to tell those apart. Returns week - 1
    when the schedule can't be read, which is the safe answer.
    """
    games = await get_week_schedule(season, week)
    if games and all(g["state"] == "post" for g in games.values()):
        return week
    return week - 1
