"""NFL highlights from YouTube, matched to the players a user actually owns.

Why YouTube and not ESPN: ESPN's internal API serves per-play clips tagged with the
same athlete ids we already store, which is a better fit technically, but those are
undocumented endpoints serving clips that expire in 48 hours, and playing the bare mp4
strips the ad bundle they ship with. YouTube's iframe embed is the licensed way to show
this content, so it is the only one that survives the app being sold.

Quota: the free tier allows 10,000 units/day. search.list costs 100 per call, so we never
use it. playlistItems.list costs 1 and returns 50, which makes a full week of uploads
(~400 items) cost 8 units. Polling for new items costs 1.
"""
import logging
import re
from typing import Optional

import httpx

from config import YOUTUBE_API_KEY
from services.cache_service import TTLCache
from services.utils import normalize_name

logger = logging.getLogger(__name__)

API = "https://www.googleapis.com/youtube/v3"
NFL_UPLOADS_PLAYLIST = "UUDVYQ4Zhbm3S2dlz7P1GBDg"  # the @NFL channel's uploads

_cache = TTLCache(default_ttl_hours=1.0)

# Titles name teams in full ("Los Angeles Rams"); rosters store Sleeper abbreviations.
# Keyed on the nickname because that is the one part a title never abbreviates.
NICKNAME_TO_ABBR = {
    "cardinals": "ARI", "falcons": "ATL", "ravens": "BAL", "bills": "BUF",
    "panthers": "CAR", "bears": "CHI", "bengals": "CIN", "browns": "CLE",
    "cowboys": "DAL", "broncos": "DEN", "lions": "DET", "packers": "GB",
    "texans": "HOU", "colts": "IND", "jaguars": "JAX", "chiefs": "KC",
    "raiders": "LV", "chargers": "LAC", "rams": "LAR", "dolphins": "MIA",
    "vikings": "MIN", "patriots": "NE", "saints": "NO", "giants": "NYG",
    "jets": "NYJ", "eagles": "PHI", "steelers": "PIT", "49ers": "SF",
    "seahawks": "SEA", "buccaneers": "TB", "titans": "TEN", "commanders": "WAS",
}


def team_abbr(name: str) -> Optional[str]:
    """"Los Angeles Rams" -> "LAR". None when the nickname is not recognised."""
    for word in reversed((name or "").split()):
        if (abbr := NICKNAME_TO_ABBR.get(word.strip(".").lower())):
            return abbr
    return None

# ── Title classification ──────────────────────────────────────────────────────
# The channel posts roughly 45 videos a day and only a fraction are highlights, so
# every title is sorted before anything reaches a page. Patterns are built from 400
# real uploads (tests/fixtures/nfl_uploads.json); that fixture is the regression test.

# Shows, previews and promos. Checked before the play fallback, never before the
# structured patterns: "Game of the Week ... FULL GAME" must not eat a real highlight.
NOISE = re.compile(
    r"power rankings|preview|injury report|nfl daily|nfl report|full game|fantasy football"
    r"|press conference|interview|mic'd up|mic’d up|training camp|combine|nfl draft"
    r"|race to the end ?zone|powered by|presented by|sweepstakes|giveaway"
    r"|reacts?\b|reaction|was hype|speaks|show\b|podcast|top 10 .* of all time",
    re.I,
)
# "Jared Goff's best throws from 4-TD game vs. Bills | Week 2"
PLAYER_REEL = re.compile(
    r"^(?P<player>[A-Z][\w'’.\-]*(?: [A-Z][\w'’.\-]*){1,3})"
    r"(?:'s|’s|'|’) best (?:throws|catches|plays|runs|moments|hits|tackles)\b"
    r"(?:.*?\bvs\.? (?P<opponent>[\w .'\-]+?)\s*(?:\||$))?",
)
# "Cincinnati Bengals vs Houston Texans Game Highlights | 2026 NFL Season Week 2"
GAME = re.compile(r"^(?P<away>.+?) vs\.? (?P<home>.+?) Game Highlights", re.I)
COMPILATION = re.compile(
    r"every touchdown of week \d+|top \d+ plays of week \d+|top \d+ plays"
    r"|best plays? from every team in week \d+|best plays from sunday",
    re.I,
)
WEEK = re.compile(r"week (\d+)", re.I)


def classify_title(title: str) -> dict:
    """Sort one upload into reel | compilation | game | play | noise.

    "play" is a candidate, not a verdict: those titles are unstructured, so the caller
    confirms them by matching a rostered player's full name. That check also discards
    team-result clips ("Packers Take the Win in OT") without needing a rule for them.
    """
    week = int(m.group(1)) if (m := WEEK.search(title)) else None

    if m := PLAYER_REEL.match(title):
        return {"kind": "reel", "week": week, "player": m.group("player"),
                "opponent": (m.group("opponent") or "").strip() or None}
    if COMPILATION.search(title):
        return {"kind": "compilation", "week": week}
    if m := GAME.match(title):
        return {"kind": "game", "week": week,
                "teams": [m.group("away").strip(), m.group("home").strip()]}
    if NOISE.search(title):
        return {"kind": "noise", "week": week}
    return {"kind": "play", "week": week}


def match_players(title: str, roster: dict[str, str]) -> list[str]:
    """Which rostered players a title names. `roster` maps normalized name -> player_id.

    Full names only. A bare surname cannot be resolved (the league has a dozen
    Williamses) and guessing wrong shows a manager another player's touchdown, which is
    worse than showing nothing.
    """
    hay = normalize_name(title)
    return [pid for name, pid in roster.items() if name and name in hay]


# ── Fetching ──────────────────────────────────────────────────────────────────

async def get_channel_uploads(max_items: int = 200, force: bool = False) -> list[dict]:
    """Recent uploads, newest first: [{video_id, title, published_at, thumbnail}].

    Returns [] when no API key is set, so the feature degrades to an empty page rather
    than an error. Cached an hour: the channel posts often, but not every minute.
    """
    if not YOUTUBE_API_KEY:
        return []
    key = f"yt_uploads_{max_items}"
    if not force and (hit := _cache.get(key)) is not None:
        return hit

    items, token = [], None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            while len(items) < max_items:
                params = {"part": "snippet,contentDetails", "playlistId": NFL_UPLOADS_PLAYLIST,
                          "maxResults": 50, "key": YOUTUBE_API_KEY}
                if token:
                    params["pageToken"] = token
                resp = await client.get(f"{API}/playlistItems", params=params)
                resp.raise_for_status()
                data = resp.json()
                for it in data.get("items", []):
                    snip, det = it.get("snippet") or {}, it.get("contentDetails") or {}
                    vid = det.get("videoId")
                    if not vid:
                        continue
                    items.append({
                        "video_id": vid,
                        "title": snip.get("title") or "",
                        "published_at": det.get("videoPublishedAt"),
                        # Free, no extra call. maxres is missing on many videos; hq always exists.
                        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    })
                token = data.get("nextPageToken")
                if not token:
                    break
    except Exception as e:
        logger.error(f"[YouTube] uploads fetch failed: {e}")
        return _cache.get(key) or []

    return _cache.set(key, items[:max_items], ttl_hours=1)


async def playable_in_embed(video_ids: list[str]) -> dict[str, bool]:
    """Which videos will actually play inside an iframe on our own site.

    Neither the Data API's status.embeddable nor oEmbed answers this: both say yes for
    every NFL upload, while the rights holder separately blocks playback off YouTube.
    Game highlights, player reels and play clips are blocked; the weekly compilations
    are not. The only way to know is to ask the embed page, which costs no API quota.

    Cached for a day and probed concurrently, since a page shows a few dozen videos.
    """
    out, missing = {}, []
    for vid in video_ids:
        hit = _cache.get(f"yt_embed_{vid}")
        (out.__setitem__(vid, hit) if hit is not None else missing.append(vid))
    if not missing:
        return out

    async def probe(client: httpx.AsyncClient, vid: str) -> tuple[str, bool]:
        try:
            r = await client.get(f"https://www.youtube.com/embed/{vid}",
                                 headers={"Referer": "https://fantas.ai/"})
            return vid, "blocked it from display" not in r.text
        except Exception:
            return vid, False  # assume blocked: a link out always works, a dead player does not

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            import asyncio
            for vid, ok in await asyncio.gather(*(probe(client, v) for v in missing)):
                out[vid] = _cache.set(f"yt_embed_{vid}", ok, ttl_hours=24)
    except Exception as e:
        logger.warning(f"[YouTube] embed probe failed: {e}")
        for vid in missing:
            out.setdefault(vid, False)
    return out


async def highlights_for(roster: dict[str, str], week: Optional[int] = None,
                         since: Optional[str] = None, until: Optional[str] = None,
                         max_items: int = 200) -> dict:
    """The tape for one roster: reels and plays naming your players, plus the game
    highlights and weekly compilations that cover everyone else.

    `roster` maps normalized player name -> player_id. `since`/`until` are ISO dates
    bounding the week, and they are not optional in practice: most titles carry their
    week ("| Week 2") but some do not, and play clips never do, so without a date window
    an untagged clip leaks into every week. Callers derive the window from nfl_state.
    """
    uploads = await get_channel_uploads(max_items)
    out: dict[str, list] = {"reels": [], "plays": [], "games": [], "compilations": []}

    for u in uploads:
        c = classify_title(u["title"])
        kind = c["kind"]
        if kind == "noise":
            continue
        if week is not None and c["week"] is not None and c["week"] != week:
            continue
        # Untagged clips are placed by when they were posted instead.
        pub = (u.get("published_at") or "")[:10]
        if since and pub and pub < since:
            continue
        if until and pub and pub > until:
            continue
        entry = {**u, **c}

        if kind in ("reel", "play"):
            pids = match_players(u["title"], roster)
            if not pids:
                continue
            entry["player_ids"] = pids
            out["reels" if kind == "reel" else "plays"].append(entry)
        elif kind == "game":
            out["games"].append(entry)
        elif kind == "compilation":
            out["compilations"].append(entry)

    return out
