"""
RSS news source (Phase 5+).

Pulls general NFL news from a handful of high-signal RSS feeds and keeps only the items
that mention one of the user's rostered/starred players. General feeds aren't player-keyed,
so the match happens here: each entry's title+summary is scanned for a tracked player's full
name, and matched items are emitted in the same raw shape the other news sources use
(`player_name`, `headline`, `news_body`, `published_at`, `source_url`, `source`) so
`news_scraper_service` resolves, dedupes, rule-filters, and tiers them like any other source.

Scoping to the tracked-name set (not all of NFL) is what keeps the feed relevant and bounded
a league-wide RSS dump would be almost entirely noise.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import feedparser
import httpx

from services.utils import normalize_name
from services.cache_service import TTLCache

logger = logging.getLogger(__name__)

# (source label, feed URL). Labels surface as `source` on the news card.
# ESPN is intentionally NOT here: its public RSS is deprecated (returns HTTP 202 with
# zero entries), and ESPN news already flows into the pipeline via the Sports API
# (nfl_service.get_espn_news), so ESPN coverage is present, just not through RSS.
FEEDS: list[tuple[str, str]] = [
    ("PFT",   "https://profootballtalk.nbcsports.com/feed/"),
    ("CBS",   "https://www.cbssports.com/rss/headlines/nfl/"),
    ("YAHOO", "https://sports.yahoo.com/nfl/rss/"),
]

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
_TAG_RE = re.compile(r"<[^>]+>")
_MAX_BODY = 2000  # PlayerNews.news_body cap

CACHE_TTL_MINUTES = 30
_cache = TTLCache()
_KEY = "rss_entries"  # all feeds fetched together, so one key


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


def _parse_published(entry) -> Optional[datetime]:
    """RSS gives a struct_time; normalize to a naive UTC datetime (matches the schema)."""
    st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not st:
        return None
    try:
        return datetime(*st[:6], tzinfo=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


async def _fetch_feed(client: httpx.AsyncClient, source: str, url: str) -> list:
    """Fetch + parse one feed. Failures are isolated, a dead feed never sinks the batch."""
    try:
        resp = await client.get(url, headers={"User-Agent": _UA}, timeout=10.0)
        resp.raise_for_status()
        # feedparser is blocking (pure CPU parse), keep it off the event loop.
        parsed = await asyncio.to_thread(feedparser.parse, resp.content)
        return [(source, e) for e in parsed.entries]
    except Exception as e:
        logger.warning(f"[RSS] {source} feed failed ({url}): {e}")
        return []


def _build_matcher(player_names: Iterable[str]) -> list[tuple[str, str]]:
    """Return (normalized_name, canonical_name) pairs for substring matching.

    Matching on the normalized FULL name ('nico collins') keeps false positives low,
    a lone first or last name would over-match.
    """
    seen: dict[str, str] = {}
    for name in player_names:
        norm = normalize_name(name)
        if len(norm) >= 6 and norm not in seen:  # skip too-short/ambiguous names
            seen[norm] = name
    return list(seen.items())


async def fetch_rss_news(
    player_names: Iterable[str],
    force_refresh: bool = False,
) -> list[dict]:
    """Fetch all feeds and return raw news items for entries mentioning a tracked player.

    One item per (entry, first matched player), attaching to the first match avoids a
    source_url dedup collision when an article names two of your players.
    """
    matcher = _build_matcher(player_names)
    if not matcher:
        return []  # nobody to match against → skip the network entirely

    entries = None if force_refresh else _cache.get(_KEY)
    if entries is None:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            results = await asyncio.gather(*[_fetch_feed(client, s, u) for s, u in FEEDS])
        entries = _cache.set_minutes(_KEY, [pair for feed in results for pair in feed], CACHE_TTL_MINUTES)

    items: list[dict] = []
    for source, entry in entries:
        title = getattr(entry, "title", "") or ""
        summary = _strip_html(getattr(entry, "summary", "") or "")
        haystack = normalize_name(f"{title} {summary}")

        matched_name = next((canon for norm, canon in matcher if norm in haystack), None)
        if not matched_name:
            continue

        link = getattr(entry, "link", None)
        if not link:
            continue  # no URL → can't dedupe or link out; drop it

        items.append({
            "player_name": matched_name,
            "source": source,
            "headline": title.strip(),
            "news_body": summary[:_MAX_BODY] or None,
            "published_at": _parse_published(entry),
            "source_url": link,
        })

    logger.info(f"[RSS] {len(items)} matched items across {len(FEEDS)} feeds")
    return items
