"""
Weekly recap: actual points vs. projections for one roster in one league-week.

Pure functions, no I/O. The router fetches the Sleeper matchup + league settings and
the stored projections, then calls build_recap().
"""
from typing import Callable, Optional

SOURCES = ("sleeper", "espn", "fp", "weighted")

# Which positions can fill each Sleeper roster slot. BN/IR/TAXI are not lineup slots.
SLOT_ELIGIBLE: dict[str, set[str]] = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}, "DEF": {"DEF"},
    "FLEX": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"WR", "RB"},
    "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
}


def best_lineup(players: list[dict], slots: list[str], score: Callable[[dict], float]) -> list[dict]:
    """Highest-scoring legal lineup: fill the narrowest slots first, then flex slots,
    each with the best unused eligible player."""
    # ponytail: greedy narrowest-first is exact for standard FLEX/SUPER_FLEX layouts;
    # swap in a small assignment solver if a league ever mixes overlapping flex types.
    lineup, used = [], set()
    for slot in sorted((s for s in slots if s in SLOT_ELIGIBLE), key=lambda s: len(SLOT_ELIGIBLE[s])):
        pool = [p for p in players if p["position"] in SLOT_ELIGIBLE[slot] and p["player_id"] not in used]
        if pool:
            pick = max(pool, key=score)
            used.add(pick["player_id"])
            lineup.append({**pick, "slot": slot})
    return lineup


def _actual(p: dict) -> float:
    return p["actual"] or 0.0


def build_recap(matchup: dict, roster_positions: list[str], projections: dict[str, dict],
                player_info: dict[str, dict], week: int, season: int, final: bool) -> dict:
    """
    matchup          Sleeper matchup entry for this roster (starters, players, players_points, points)
    roster_positions league slots, e.g. ["QB","RB","RB","WR","WR","TE","FLEX","K","DEF","BN",...]
    projections      {player_id: {"sleeper": x, "espn": x, "fp": x, "weighted": x}} for this week
    player_info      {player_id: {"name": str, "position": str, "nfl_team": str}}
    """
    points = matchup.get("players_points") or {}
    starters = [s for s in (matchup.get("starters") or []) if s and s != "0"]

    players = []
    for pid in matchup.get("players") or []:
        info = player_info.get(pid, {})
        proj = projections.get(pid, {})
        actual = points.get(pid)
        players.append({
            "player_id": pid,
            "name": info.get("name", pid),
            "position": info.get("position", "DEF" if pid.isalpha() else "?"),
            "nfl_team": info.get("nfl_team"),
            "started": pid in starters,
            "actual": actual,
            **{f"{s}_proj": proj.get(s) for s in SOURCES},
            "diff": round(actual - proj["weighted"], 2) if actual is not None and proj.get("weighted") is not None else None,
        })

    # Mean absolute error per source over players that have both numbers.
    accuracy = {}
    for s in SOURCES:
        errs = [abs(p["actual"] - p[f"{s}_proj"]) for p in players
                if p["actual"] is not None and p[f"{s}_proj"] is not None]
        accuracy[s] = {"mae": round(sum(errs) / len(errs), 2) if errs else None, "n": len(errs)}
    ranked = [s for s in SOURCES if s != "weighted" and accuracy[s]["n"] >= 3 and accuracy[s]["mae"] is not None]
    most_accurate = min(ranked, key=lambda s: accuracy[s]["mae"]) if ranked else None

    your_points = round(sum(_actual(p) for p in players if p["started"]), 2)
    hindsight = best_lineup(players, roster_positions, _actual)
    by_proj = best_lineup(players, roster_positions, lambda p: p["weighted_proj"] or 0.0)
    best_points = round(sum(_actual(p) for p in hindsight), 2)
    proj_points = round(sum(_actual(p) for p in by_proj), 2)

    slot_order = {pid: i for i, pid in enumerate(starters)}
    players.sort(key=lambda p: (not p["started"], slot_order.get(p["player_id"], 99), -_actual(p)))

    return {
        "week": week,
        "season": season,
        "final": final,
        "players": players,
        "accuracy": accuracy,
        "most_accurate_source": most_accurate,
        "lineup": {
            "your_points": your_points,
            "best_possible_points": best_points,
            "points_left_on_bench": round(best_points - your_points, 2),
            "projection_lineup_points": proj_points,
            "best_lineup_ids": [p["player_id"] for p in hindsight],
            "projection_lineup_ids": [p["player_id"] for p in by_proj],
        },
    }


def find_matchup(matchups: list[dict], roster_id: int) -> Optional[dict]:
    return next((m for m in matchups if m.get("roster_id") == roster_id), None)
