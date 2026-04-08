"""
nflreadpy data loader — historical stats, snap counts, depth charts.

Uses get_nfl_state() to determine the current season so this never needs
manual updates when a new NFL season starts.

All functions return empty dicts/strings on failure — never raise.
"""
import logging
from typing import Optional

import pandas as pd

from services.projection_service import get_nfl_state

logger = logging.getLogger(__name__)


def _get_seasons(completed_season: int, n: int = 3) -> list[int]:
    """Return the last n seasons ending at completed_season."""
    return list(range(completed_season - n + 1, completed_season + 1))


def _normalize_for_match(name: str) -> str:
    """Lowercase, strip punctuation — used to match nflreadpy names to ours."""
    import re
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ── Season stats ──────────────────────────────────────────────────────────────

async def get_historical_stats(player_name: str, position: str) -> dict[int, dict]:
    """
    Load season-level stats for a player by name + position.

    Returns {season: {games_played, fantasy_pts_ppr, fantasy_ppg_ppr,
                       targets, receptions, rec_yards, rec_td,
                       carries, rush_yards, rush_td,
                       pass_yards, pass_td, interceptions}}

    Uses name matching since we don't store GSIS IDs.
    Returns {} on failure.
    """
    try:
        state = await get_nfl_state()
        season_type = state["season_type"]
        current_season = state["season"]
        # During offseason, season counter has already rolled to next year
        completed_season = current_season - 1 if season_type == "off" else current_season
        seasons = _get_seasons(completed_season, n=3)

        import nflreadpy as nfl
        df: pd.DataFrame = nfl.load_player_stats(seasons).to_pandas()

        norm_target = _normalize_for_match(player_name)

        # nflreadpy uses 'player_display_name' or 'player_name'
        name_col = "player_display_name" if "player_display_name" in df.columns else "player_name"
        df["_norm_name"] = df[name_col].astype(str).apply(_normalize_for_match)
        matches = df[df["_norm_name"] == norm_target]

        # Further filter by position if column exists
        if "position" in df.columns and position:
            pos_matches = matches[matches["position"].str.upper() == position.upper()]
            if not pos_matches.empty:
                matches = pos_matches

        if matches.empty:
            logger.debug(f"[nflreadpy] No stats found for '{player_name}' ({position})")
            return {}

        result: dict[int, dict] = {}
        for season, grp in matches.groupby("season"):
            games = int(grp["season_games_played"].sum()) if "season_games_played" in grp.columns else len(grp["week"].unique()) if "week" in grp.columns else None

            def _sum(col: str) -> Optional[float]:
                return round(float(grp[col].sum()), 1) if col in grp.columns else None

            def _ppr_ppg(total_pts, games_played) -> Optional[float]:
                if total_pts and games_played and games_played > 0:
                    return round(total_pts / games_played, 1)
                return None

            fp_total = _sum("fantasy_points_ppr")
            result[int(season)] = {
                "games_played": games,
                "fantasy_pts_ppr": fp_total,
                "fantasy_ppg_ppr": _ppr_ppg(fp_total, games),
                "targets": _sum("targets"),
                "receptions": _sum("receptions"),
                "rec_yards": _sum("receiving_yards"),
                "rec_td": _sum("receiving_tds"),
                "carries": _sum("carries"),
                "rush_yards": _sum("rushing_yards"),
                "rush_td": _sum("rushing_tds"),
                "pass_yards": _sum("passing_yards"),
                "pass_td": _sum("passing_tds"),
                "interceptions": _sum("interceptions"),
            }

        return result

    except Exception as e:
        logger.error(f"[nflreadpy] get_historical_stats failed for '{player_name}': {e}")
        return {}


# ── Snap counts ───────────────────────────────────────────────────────────────

async def get_recent_snap_share(player_name: str) -> dict:
    """
    Return avg snap % and target share for the last 4 weeks available.

    Returns {"snap_pct": float|None, "target_share": float|None,
             "weeks_sampled": int, "season": int}
    Returns {} on failure.
    """
    try:
        state = await get_nfl_state()
        season_type = state["season_type"]
        current_season = state["season"]
        completed_season = current_season - 1 if season_type == "off" else current_season

        import nflreadpy as nfl
        snap_df: pd.DataFrame = nfl.load_snap_counts([completed_season]).to_pandas()

        norm_target = _normalize_for_match(player_name)
        name_col = "player_name" if "player_name" in snap_df.columns else "player_display_name"
        snap_df["_norm"] = snap_df[name_col].astype(str).apply(_normalize_for_match)
        player_snaps = snap_df[snap_df["_norm"] == norm_target]

        if player_snaps.empty:
            return {}

        # Last 4 weeks available
        recent = player_snaps.nlargest(4, "week") if "week" in player_snaps.columns else player_snaps

        snap_pct_col = "offense_pct" if "offense_pct" in recent.columns else None
        snap_pct = round(float(recent[snap_pct_col].mean()), 3) if snap_pct_col else None

        return {
            "snap_pct": snap_pct,
            "weeks_sampled": len(recent),
            "season": int(completed_season),
        }

    except Exception as e:
        logger.error(f"[nflreadpy] get_recent_snap_share failed for '{player_name}': {e}")
        return {}


# ── Gemini context string ─────────────────────────────────────────────────────

async def build_stats_context(player_name: str, position: str) -> str:
    """
    Build a concise stats context string for use in Gemini prompts.

    Example output:
      "2023: 15 games, 1,234 rec yds, 8 TDs, 22.4 PPR/g.
       2024: 16 games, 1,456 rec yds, 10 TDs, 24.1 PPR/g.
       2025 (8 games): 621 rec yds, 4 TDs, 18.3 PPR/g. Recent snap share: 87%."

    Returns "No historical stats available." on failure or no data.
    """
    stats, snaps = await _gather_stats_and_snaps(player_name, position)

    if not stats:
        return "No historical stats available."

    lines = []
    for season in sorted(stats.keys()):
        s = stats[season]
        games = s.get("games_played") or "?"
        ppg = s.get("fantasy_ppg_ppr")
        ppg_str = f"{ppg} PPR/g" if ppg else ""

        # Build stat line based on position
        pos_upper = position.upper() if position else ""
        if pos_upper == "QB":
            parts = _qb_line(s)
        elif pos_upper in ("RB",):
            parts = _rb_line(s)
        elif pos_upper in ("WR", "TE"):
            parts = _receiver_line(s)
        else:
            parts = _generic_line(s)

        stat_str = ", ".join(filter(None, parts))
        lines.append(f"{season} ({games} games): {stat_str}{', ' + ppg_str if ppg_str else ''}.")

    if snaps:
        snap_pct = snaps.get("snap_pct")
        if snap_pct is not None:
            weeks = snaps.get("weeks_sampled", 0)
            lines.append(f"Recent snap share (last {weeks} weeks): {round(snap_pct * 100, 1)}%.")

    return " ".join(lines) if lines else "No historical stats available."


async def _gather_stats_and_snaps(player_name: str, position: str):
    """Fetch stats and snap counts concurrently."""
    import asyncio
    stats, snaps = await asyncio.gather(
        get_historical_stats(player_name, position),
        get_recent_snap_share(player_name),
    )
    return stats, snaps


def _qb_line(s: dict) -> list:
    parts = []
    if s.get("pass_yards"):
        parts.append(f"{int(s['pass_yards'])} pass yds")
    if s.get("pass_td"):
        parts.append(f"{int(s['pass_td'])} pass TDs")
    if s.get("interceptions"):
        parts.append(f"{int(s['interceptions'])} INTs")
    if s.get("rush_yards"):
        parts.append(f"{int(s['rush_yards'])} rush yds")
    return parts


def _rb_line(s: dict) -> list:
    parts = []
    if s.get("rush_yards"):
        parts.append(f"{int(s['rush_yards'])} rush yds")
    if s.get("rush_td"):
        parts.append(f"{int(s['rush_td'])} rush TDs")
    if s.get("receptions"):
        parts.append(f"{int(s['receptions'])} rec")
    if s.get("rec_yards"):
        parts.append(f"{int(s['rec_yards'])} rec yds")
    return parts


def _receiver_line(s: dict) -> list:
    parts = []
    if s.get("targets"):
        parts.append(f"{int(s['targets'])} tgts")
    if s.get("receptions"):
        parts.append(f"{int(s['receptions'])} rec")
    if s.get("rec_yards"):
        parts.append(f"{int(s['rec_yards'])} rec yds")
    if s.get("rec_td"):
        parts.append(f"{int(s['rec_td'])} TDs")
    return parts


def _generic_line(s: dict) -> list:
    parts = []
    if s.get("fantasy_pts_ppr"):
        parts.append(f"{s['fantasy_pts_ppr']} PPR pts total")
    return parts
