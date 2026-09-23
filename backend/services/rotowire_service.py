import logging
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Optional
from services.cache_service import TTLCache

logger = logging.getLogger(__name__)

ROTOWIRE_NEWS_URL = "https://www.rotowire.com/football/news.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

CACHE_TTL_MINUTES = 30  # game days; caller can override
_cache = TTLCache()
_KEY = "rotowire_news"  # one feed, so one key


def scrape_rotowire_news(force_refresh: bool = False, ttl_minutes: int = CACHE_TTL_MINUTES) -> list[dict]:
    """
    Scrape the public RotoWire NFL news feed.
    Returns list of dicts: {player_name, headline, news_body, published_at, source_url, source}.
    Does NOT scrape the paywalled ANALYSIS section, Gemini generates analysis instead.
    """
    if not force_refresh and (hit := _cache.get(_KEY)) is not None:
        return hit

    items = []
    for attempt in range(3):
        try:
            resp = requests.get(ROTOWIRE_NEWS_URL, headers=HEADERS, timeout=15)
            if resp.status_code == 403:
                logger.warning(f"[RotoWire] 403 Forbidden on attempt {attempt + 1}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            items = _parse_news_page(resp.text)
            break
        except Exception as e:
            logger.error(f"[RotoWire] scrape attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)

    _cache.set_minutes(_KEY, items, ttl_minutes)
    logger.info(f"[RotoWire] scraped {len(items)} news items")
    return items


def _parse_news_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # RotoWire news cards, each article is a .news-update block
    news_blocks = soup.select(".news-update")
    if not news_blocks:
        # Fallback: try generic article containers
        news_blocks = soup.select("li.player-news-item, article.news-item")

    for block in news_blocks:
        item = _parse_news_block(block)
        if item:
            items.append(item)

    return items


def _parse_news_block(block) -> Optional[dict]:
    """Parse a single RotoWire news block. Returns None if unparseable."""
    try:
        # Player name, typically in a link within a header or player-name span
        player_el = (
            block.select_one(".news-update__player-link")
            or block.select_one(".player-name")
            or block.select_one("a.player-news-player-name")
        )
        if not player_el:
            return None
        player_name = player_el.get_text(strip=True)
        if not player_name:
            return None

        # Headline, bold summary line
        headline_el = (
            block.select_one(".news-update__headline")
            or block.select_one(".news-headline")
            or block.select_one("h4")
        )
        headline = headline_el.get_text(strip=True) if headline_el else ""

        # News body, the NEWS section only, NOT the ANALYSIS section
        # RotoWire labels these as separate paragraphs: first is news, second is analysis
        body_el = (
            block.select_one(".news-update__news")
            or block.select_one(".news-body")
        )
        if body_el:
            news_body = body_el.get_text(strip=True)
        else:
            # Fallback: grab all <p> tags but skip any labeled "ANALYSIS"
            paragraphs = block.find_all("p")
            news_paragraphs = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                # Skip the paywalled analysis paragraph
                if text.lower().startswith("analysis:") or "ANALYSIS" in (p.get("class") or []):
                    break
                if text:
                    news_paragraphs.append(text)
            news_body = " ".join(news_paragraphs)

        # Truncate body to 2000 chars
        news_body = news_body[:2000] if news_body else None

        # Source URL, canonical link to the news item
        link_el = block.select_one("a[href*='/football/news/']") or block.find("a", href=True)
        source_url = None
        if link_el:
            href = link_el.get("href", "")
            if href.startswith("http"):
                source_url = href
            elif href:
                source_url = f"https://www.rotowire.com{href}"

        # Published timestamp, RotoWire uses relative or absolute time strings
        time_el = block.select_one("time") or block.select_one(".news-update__timestamp")
        published_at = _parse_timestamp(time_el)

        if not headline and not news_body:
            return None

        return {
            "player_name": player_name,
            "headline": headline or f"Update: {player_name}",
            "news_body": news_body,
            "published_at": published_at,
            "source_url": source_url,
            "source": "ROTOWIRE",
        }
    except Exception as e:
        logger.warning(f"[RotoWire] failed to parse news block: {e}")
        return None


def _parse_timestamp(time_el) -> Optional[datetime]:
    """Parse a <time> element or text into a datetime. Returns None if unparseable."""
    if time_el is None:
        return None

    # Try <time datetime="..."> attribute first (ISO format)
    dt_attr = time_el.get("datetime", "")
    if dt_attr:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(dt_attr, fmt).replace(tzinfo=None)
            except ValueError:
                continue

    # Fallback: parse text like "2h ago", "Jan 15", "Yesterday"
    text = time_el.get_text(strip=True).lower()
    now = datetime.utcnow()

    match = re.match(r"(\d+)h ago", text)
    if match:
        return now - timedelta(hours=int(match.group(1)))

    match = re.match(r"(\d+)m ago", text)
    if match:
        return now - timedelta(minutes=int(match.group(1)))

    if "yesterday" in text:
        return now - timedelta(days=1)

    return None
