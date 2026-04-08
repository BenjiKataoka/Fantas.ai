"""
ADP fetching and trend calculation.

Sources:
  - Fantasy Football Calculator (FFC): public JSON API, no auth
  - FantasyPros: scraping, PPR

Daily snapshots stored in player_adp_history.
ADP trend = compare today vs 14 days ago across both sources.
  RISING  = improved (lower ADP) by > 2 positions on average
  FALLING = worsened (higher ADP) by > 2 positions on average
  STABLE  = within ±2 positions

Never raises — returns empty dict / STABLE on failure.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
import requests
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.tracker import PlayerADPHistory
from services.utils import normalize_name

logger = logging.getLogger(__name__)

FFC_URL = "https://fantasyfootballcalculator.com/api/v1/adp/ppr?teams=12&year={year}"
FP_ADP_URL = "https://www.fantasypros.com/nfl/adp/overall.php?scoring=PPR"

FFC_SOURCE = "FFC"
FP_SOURCE = "FANTASYPROS"

# In-memory cache: {source: {"data": [...], "fetched_at": datetime}}
_adp_cache: dict = {}
CACHE_TTL_HOURS = 24


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_and_store_adp(player_id: str, player_name: str, db: AsyncSession) -> dict:
    """
    Fetch today's ADP from FFC + FantasyPros for a player and store a snapshot
    in player_adp_history. Returns {ffc_adp, fp_adp} — values are None if not found.

    Prunes entries older than 30 days for this player to keep the table lean.
    """
    ffc_data = await _get_ffc_adp()
    fp_data = _get_fp_adp()

    norm = normalize_name(player_name)
    ffc_entry = _find_in_ffc(ffc_data, norm)
    fp_entry = _find_in_fp(fp_data, norm)

    now = datetime.utcnow()

    if ffc_entry:
        db.add(PlayerADPHistory(
            player_id=player_id,
            source=FFC_SOURCE,
            adp=ffc_entry.get("adp"),
            adp_stdev=ffc_entry.get("stdev"),
            position_rank=ffc_entry.get("position_rank"),
            overall_rank=ffc_entry.get("overall_rank"),
            recorded_at=now,
        ))

    if fp_entry:
        db.add(PlayerADPHistory(
            player_id=player_id,
            source=FP_SOURCE,
            adp=fp_entry.get("adp"),
            position_rank=fp_entry.get("position_rank"),
            overall_rank=fp_entry.get("overall_rank"),
            recorded_at=now,
        ))

    await db.flush()
    await _prune_old_adp(player_id, db)

    return {
        "ffc_adp": ffc_entry.get("adp") if ffc_entry else None,
        "fp_adp": fp_entry.get("adp") if fp_entry else None,
    }


async def compute_adp_trend(player_id: str, db: AsyncSession) -> dict:
    """
    Calculate the 14-day ADP trend for a player.

    Returns:
      {
        "trend": "RISING" | "FALLING" | "STABLE",
        "delta": float,      # avg position change (negative = improving)
        "today_avg": float,  # avg ADP across sources today
        "then_avg": float,   # avg ADP 14 days ago
      }

    Returns {"trend": "STABLE", "delta": 0.0} if insufficient data.
    """
    try:
        cutoff_recent = datetime.utcnow() - timedelta(days=2)
        cutoff_old = datetime.utcnow() - timedelta(days=16)
        window_start = datetime.utcnow() - timedelta(days=14)

        # Recent entries (last 2 days)
        stmt_recent = (
            select(PlayerADPHistory)
            .where(
                PlayerADPHistory.player_id == player_id,
                PlayerADPHistory.recorded_at >= cutoff_recent,
            )
        )
        # Entries from ~14 days ago (within a 2-day window around 14 days back)
        stmt_old = (
            select(PlayerADPHistory)
            .where(
                PlayerADPHistory.player_id == player_id,
                PlayerADPHistory.recorded_at >= cutoff_old,
                PlayerADPHistory.recorded_at < window_start,
            )
        )

        recent_result = await db.execute(stmt_recent)
        old_result = await db.execute(stmt_old)
        recent_rows = recent_result.scalars().all()
        old_rows = old_result.scalars().all()

        recent_adps = [r.adp for r in recent_rows if r.adp is not None]
        old_adps = [r.adp for r in old_rows if r.adp is not None]

        if not recent_adps or not old_adps:
            return {"trend": "STABLE", "delta": 0.0, "today_avg": None, "then_avg": None}

        today_avg = sum(recent_adps) / len(recent_adps)
        then_avg = sum(old_adps) / len(old_adps)
        delta = today_avg - then_avg  # negative = ADP improved (lower pick number)

        if delta < -2:
            trend = "RISING"
        elif delta > 2:
            trend = "FALLING"
        else:
            trend = "STABLE"

        return {
            "trend": trend,
            "delta": round(delta, 1),
            "today_avg": round(today_avg, 1),
            "then_avg": round(then_avg, 1),
        }

    except Exception as e:
        logger.error(f"[ADP] compute_adp_trend failed for player_id={player_id}: {e}")
        return {"trend": "STABLE", "delta": 0.0, "today_avg": None, "then_avg": None}


# ── FFC fetch ─────────────────────────────────────────────────────────────────

async def _get_ffc_adp() -> list[dict]:
    cached = _adp_cache.get(FFC_SOURCE)
    if cached and datetime.utcnow() < cached["expires"]:
        return cached["data"]

    try:
        year = date.today().year
        url = FFC_URL.format(year=year)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            data = resp.json()

        players = data.get("players", [])
        _adp_cache[FFC_SOURCE] = {
            "data": players,
            "expires": datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS),
        }
        logger.info(f"[ADP] FFC loaded {len(players)} players")
        return players

    except Exception as e:
        logger.error(f"[ADP] FFC fetch failed: {e}")
        return []


def _find_in_ffc(data: list[dict], norm_name: str) -> Optional[dict]:
    for p in data:
        name = p.get("name") or p.get("player_name") or ""
        if normalize_name(name) == norm_name:
            return {
                "adp": p.get("adp"),
                "stdev": p.get("stdev"),
                "position_rank": p.get("position_rank"),
                "overall_rank": p.get("pick"),
            }
    return None


# ── FantasyPros ADP fetch ─────────────────────────────────────────────────────

def _get_fp_adp() -> list[dict]:
    cached = _adp_cache.get(FP_SOURCE)
    if cached and datetime.utcnow() < cached["expires"]:
        return cached["data"]

    try:
        resp = requests.get(
            FP_ADP_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
        players = _parse_fp_adp(resp.text)
        _adp_cache[FP_SOURCE] = {
            "data": players,
            "expires": datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS),
        }
        logger.info(f"[ADP] FantasyPros ADP loaded {len(players)} players")
        return players

    except Exception as e:
        logger.error(f"[ADP] FantasyPros ADP fetch failed: {e}")
        return []


def _parse_fp_adp(html: str) -> list[dict]:
    """Parse the FantasyPros ADP table. Returns list of player dicts."""
    players = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", {"id": "data"})
        if not table:
            return []

        rows = table.find("tbody").find_all("tr")
        for i, row in enumerate(rows):
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            try:
                name_tag = cols[1].find("a")
                if not name_tag:
                    continue
                name = name_tag.text.strip()
                adp_text = cols[-1].text.strip().replace(",", "")
                adp = float(adp_text) if adp_text else None
                players.append({
                    "name": name,
                    "adp": adp,
                    "overall_rank": i + 1,
                })
            except (ValueError, IndexError):
                continue
    except Exception as e:
        logger.error(f"[ADP] FP parse error: {e}")
    return players


def _find_in_fp(data: list[dict], norm_name: str) -> Optional[dict]:
    for p in data:
        if normalize_name(p.get("name", "")) == norm_name:
            return {
                "adp": p.get("adp"),
                "position_rank": p.get("position_rank"),
                "overall_rank": p.get("overall_rank"),
            }
    return None


# ── Pruning ───────────────────────────────────────────────────────────────────

async def _prune_old_adp(player_id: str, db: AsyncSession) -> None:
    """Delete ADP snapshots older than 30 days for this player."""
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        stmt = select(PlayerADPHistory).where(
            PlayerADPHistory.player_id == player_id,
            PlayerADPHistory.recorded_at < cutoff,
        )
        result = await db.execute(stmt)
        old_rows = result.scalars().all()
        for row in old_rows:
            await db.delete(row)
        await db.flush()
    except Exception as e:
        logger.warning(f"[ADP] Prune failed for player_id={player_id}: {e}")
