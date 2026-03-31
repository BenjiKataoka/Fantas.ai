"""
FantasyPros projection scraper.

Scrapes PPR weekly projections for QB/RB/WR/TE/K.
Returns {normalized_player_name: projected_points}.
Uses asyncio.sleep between position scrapes to avoid rate limiting.
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from services.utils import normalize_name

logger = logging.getLogger(__name__)

FP_BASE = "https://www.fantasypros.com/nfl/projections"
POSITIONS = ["qb", "rb", "wr", "te", "k"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# 4h cache — never scrape more than once per 4h window
_cache: dict = {}
CACHE_TTL_HOURS = 4


def _get_cache(key: str):
    entry = _cache.get(key)
    if entry and datetime.utcnow() < entry[1]:
        return entry[0]
    return None


def _set_cache(key: str, data, ttl_hours: int = CACHE_TTL_HOURS):
    _cache[key] = (data, datetime.utcnow() + timedelta(hours=ttl_hours))


async def get_fp_projections(week: int) -> dict[str, float]:
    """
    Scrapes FantasyPros PPR projections for all skill positions for a given week.
    Returns {normalized_player_name: projected_points}.
    Sleeps 1-2s between each position to avoid rate limiting (5 positions = ~5-10s total).
    Returns empty dict during offseason — FantasyPros tables are empty until season starts.
    """
    cache_key = f"fp_proj_{week}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    all_projections: dict[str, float] = {}

    for i, pos in enumerate(POSITIONS):
        if i > 0:
            # Non-blocking sleep between position scrapes
            await asyncio.sleep(random.uniform(1, 2))

        try:
            data = await _scrape_position(pos, week)
            all_projections.update(data)
            logger.info(f"[FP] Scraped {len(data)} {pos.upper()} projections for week {week}")
        except Exception as e:
            logger.error(f"[FP] Failed to scrape {pos.upper()} for week {week}: {e}")
            # Continue with remaining positions even if one fails

    if not all_projections:
        logger.warning(
            f"[FP] No projections returned for week {week}. Expected during offseason."
        )

    _set_cache(cache_key, all_projections)
    return all_projections


async def _scrape_position(pos: str, week: int) -> dict[str, float]:
    """Scrapes a single position page. Returns {normalized_name: pts}."""
    url = f"{FP_BASE}/{pos}.php"
    params = {"scoring": "PPR", "week": week}
    resp = await _fetch_with_retry(url, params)
    return _parse_projection_table(resp.text, pos)


async def _fetch_with_retry(
    url: str,
    params: dict,
    max_attempts: int = 3,
) -> httpx.Response:
    """GET with exponential backoff retry."""
    last_exc: Exception = Exception("Unknown error")
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=HEADERS, params=params)
                resp.raise_for_status()
                return resp
        except Exception as e:
            last_exc = e
            if attempt < max_attempts - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"[FP] Attempt {attempt + 1} failed for {url}: {e}. "
                    f"Retrying in {wait:.1f}s"
                )
                await asyncio.sleep(wait)
    raise last_exc


def _parse_projection_table(html: str, pos: str) -> dict[str, float]:
    """
    Parses the FantasyPros projection table HTML.
    Finds the FPTS column dynamically from table headers.
    Returns {normalized_name: pts}.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "data"})

    if not table:
        logger.warning(f"[FP] Could not find projection table for {pos.upper()}")
        return {}

    # Locate FPTS column index from headers
    fpts_idx = None
    thead = table.find("thead")
    if thead:
        cols = [th.get_text(strip=True).upper() for th in thead.find_all("th")]
        for i, col in enumerate(cols):
            if col in ("FPTS", "FANT PTS", "PTS", "FANTASY PTS"):
                fpts_idx = i
                break

    if fpts_idx is None:
        logger.warning(f"[FP] Could not find FPTS column for {pos.upper()}")
        return {}

    projections: dict[str, float] = {}
    tbody = table.find("tbody")
    if not tbody:
        return {}

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) <= fpts_idx:
            continue

        # Player name lives inside an <a> tag in the first cell
        name_tag = cells[0].find("a", {"class": "player-name"}) or cells[0].find("a")
        if not name_tag:
            continue

        normalized = normalize_name(name_tag.get_text(strip=True))
        fpts_text = cells[fpts_idx].get_text(strip=True).replace(",", "")

        try:
            pts = float(fpts_text)
            if pts > 0:
                projections[normalized] = pts
        except ValueError:
            continue

    return projections
