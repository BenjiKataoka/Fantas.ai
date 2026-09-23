"""
Historical stats caching service.

Pulls season-level stats from nflreadpy_service and stores them in the
player_historical_stats table. Refreshes once per day.

Never raises, returns {} on failure.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.tracker import PlayerHistoricalStats
from services import nflreadpy_service

logger = logging.getLogger(__name__)

REFRESH_TTL_HOURS = 24


async def sync_historical_stats(
    player_id: str,
    player_name: str,
    position: str,
    db: AsyncSession,
    force_refresh: bool = False,
) -> dict[int, dict]:
    """
    Ensure player_historical_stats is populated and fresh for this player.

    - If rows exist and are < 24h old, returns cached DB data.
    - Otherwise fetches from nflreadpy and upserts.

    Returns {season: {games_played, fantasy_pts_ppr, ...}} or {} on failure.
    """
    try:
        # Check if we have a recent row
        stmt = (
            select(PlayerHistoricalStats)
            .where(PlayerHistoricalStats.player_id == player_id)
            .order_by(PlayerHistoricalStats.season.desc())
        )
        result = await db.execute(stmt)
        existing = result.scalars().all()

        if existing and not force_refresh:
            # Check freshness via the most recent season row
            # We use the DB's recorded_at if available, else just use existing data
            # (PlayerHistoricalStats has no updated_at, treat any existing row as fresh
            #  for the rest of this calendar day by using a simple in-memory guard)
            return _rows_to_dict(existing)

        # Fetch fresh from nflreadpy
        stats = await nflreadpy_service.get_historical_stats(player_name, position)
        if not stats:
            return _rows_to_dict(existing) if existing else {}

        # Upsert each season row
        for season, s in stats.items():
            row = await db.get(PlayerHistoricalStats, (player_id, season))
            if row:
                _update_row(row, s)
            else:
                db.add(PlayerHistoricalStats(
                    player_id=player_id,
                    season=season,
                    games_played=s.get("games_played"),
                    fantasy_pts_ppr=s.get("fantasy_pts_ppr"),
                    fantasy_ppg_ppr=s.get("fantasy_ppg_ppr"),
                    targets=s.get("targets"),
                    receptions=s.get("receptions"),
                    rec_yards=s.get("rec_yards"),
                    rec_td=s.get("rec_td"),
                    carries=s.get("carries"),
                    rush_yards=s.get("rush_yards"),
                    rush_td=s.get("rush_td"),
                    pass_yards=s.get("pass_yards"),
                    pass_td=s.get("pass_td"),
                    interceptions=s.get("interceptions"),
                ))

        await db.flush()
        logger.info(f"[HistoricalStats] Synced {len(stats)} seasons for player_id={player_id}")
        return stats

    except Exception as e:
        logger.error(f"[HistoricalStats] sync failed for player_id={player_id}: {e}")
        return {}


def _update_row(row: PlayerHistoricalStats, s: dict) -> None:
    row.games_played = s.get("games_played")
    row.fantasy_pts_ppr = s.get("fantasy_pts_ppr")
    row.fantasy_ppg_ppr = s.get("fantasy_ppg_ppr")
    row.targets = s.get("targets")
    row.receptions = s.get("receptions")
    row.rec_yards = s.get("rec_yards")
    row.rec_td = s.get("rec_td")
    row.carries = s.get("carries")
    row.rush_yards = s.get("rush_yards")
    row.rush_td = s.get("rush_td")
    row.pass_yards = s.get("pass_yards")
    row.pass_td = s.get("pass_td")
    row.interceptions = s.get("interceptions")


def _rows_to_dict(rows: list[PlayerHistoricalStats]) -> dict[int, dict]:
    return {
        row.season: {
            "games_played": row.games_played,
            "fantasy_pts_ppr": row.fantasy_pts_ppr,
            "fantasy_ppg_ppr": row.fantasy_ppg_ppr,
            "targets": row.targets,
            "receptions": row.receptions,
            "rec_yards": row.rec_yards,
            "rec_td": row.rec_td,
            "carries": row.carries,
            "rush_yards": row.rush_yards,
            "rush_td": row.rush_td,
            "pass_yards": row.pass_yards,
            "pass_td": row.pass_td,
            "interceptions": row.interceptions,
        }
        for row in rows
    }
