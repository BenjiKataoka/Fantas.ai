import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.player import Player
from models.roster import MyRoster
from models.projection import Projection
from models.user import User
from auth import get_current_user
from services.projection_service import get_nfl_state

router = APIRouter()
logger = logging.getLogger(__name__)

# Standard redraft PPR lineup (1 FLEX slot for RB/WR/TE)
LINEUP_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1}
FLEX_POSITIONS = {"RB", "WR", "TE"}
FLEX_COUNT = 1

# Margin (adjusted points) below which a decision is flagged as close
CLOSE_DECISION_MARGIN = 2.0

# Injury multiplier applied to weighted_proj before lineup ranking
INJURY_MODIFIER = {
    "Active": 1.0,
    "Questionable": 0.85,
    "Doubtful": 0.60,
    "Out": 0.0,
    "IR": 0.0,
}


def _adjusted_proj(weighted_proj: float | None, injury_status: str | None) -> float:
    """Apply injury modifier to projection. Missing projection treated as 0."""
    base = weighted_proj or 0.0
    modifier = INJURY_MODIFIER.get(injury_status or "Active", 1.0)
    return round(base * modifier, 2)


def _build_player_dict(player_row, proj_row) -> dict:
    inj = player_row.injury_status or "Active"
    wp = proj_row.weighted_proj if proj_row else None
    return {
        "player_id": player_row.player_id,
        "name": player_row.name,
        "position": player_row.position,
        "nfl_team": player_row.nfl_team,
        "injury_status": inj,
        "injury_detail": player_row.injury_detail,
        "weighted_proj": wp,
        "adjusted_proj": _adjusted_proj(wp, inj),
        "confidence_flag": proj_row.confidence_flag if proj_row else None,
        "sources_used": proj_row.sources_used if proj_row else None,
    }


def _close_decision(slot: str, starter: dict, alt: dict, margin: float) -> dict:
    # Warn louder if the recommended starter has an injury tag
    if starter["injury_status"] in ("Questionable", "Doubtful"):
        note = "Slim margin — monitor injury status closely before lock"
    else:
        note = "Slim margin — consider checking matchup before lock"
    return {
        "slot": slot,
        "start": {
            "player_id": starter["player_id"],
            "name": starter["name"],
            "adjusted_proj": starter["adjusted_proj"],
            "injury_status": starter["injury_status"],
        },
        "sit": {
            "player_id": alt["player_id"],
            "name": alt["name"],
            "adjusted_proj": alt["adjusted_proj"],
            "injury_status": alt["injury_status"],
        },
        "margin": round(margin, 2),
        "note": note,
    }


@router.get("/startsit/{week}")
async def get_start_sit(
    week: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns optimal start/sit recommendations for the given week.
    Ranks players by weighted_proj × injury modifier.
    Matchup rankings will be layered in when the regular season begins (Phase 5 enhancement).
    """
    nfl_state = await get_nfl_state()
    season = nfl_state["season"]
    season_type = nfl_state["season_type"]

    if season_type == "off":
        return {
            "week": week,
            "season": season,
            "season_type": season_type,
            "starters": [],
            "bench": [],
            "close_decisions": [],
            "offseason_note": (
                "Start/Sit recommendations are unavailable in the offseason. "
                "Check back when the regular season begins."
            ),
            "warning": None,
        }

    # Load roster with player details
    result = await db.execute(
        select(MyRoster, Player)
        .join(Player, MyRoster.player_id == Player.player_id)
        .where(MyRoster.user_id == user.id)
    )
    roster_rows = result.all()

    if not roster_rows:
        raise HTTPException(
            status_code=404,
            detail="No roster found. Sync your roster first via /api/roster.",
        )

    # Load projections for this week/season
    player_ids = [row.Player.player_id for row in roster_rows]
    proj_result = await db.execute(
        select(Projection).where(
            Projection.player_id.in_(player_ids),
            Projection.week == week,
            Projection.season == season,
        )
    )
    proj_map: dict[str, Projection] = {p.player_id: p for p in proj_result.scalars().all()}

    warning = None
    if not proj_map:
        warning = (
            f"No projections found for Week {week}. "
            "Run /api/roster to sync projections first."
        )

    # Build and group players by position
    by_position: dict[str, list] = {}
    for row in roster_rows:
        pos = row.Player.position
        if pos not in {*LINEUP_SLOTS.keys(), *FLEX_POSITIONS}:
            continue
        p = _build_player_dict(row.Player, proj_map.get(row.Player.player_id))
        by_position.setdefault(pos, []).append(p)

    for pos in by_position:
        by_position[pos].sort(key=lambda x: x["adjusted_proj"], reverse=True)

    starters: list[dict] = []
    bench_ids: set[str] = set()
    close_decisions: list[dict] = []

    # Fill positional slots
    for pos, count in LINEUP_SLOTS.items():
        pool = by_position.get(pos, [])
        for i in range(count):
            if i >= len(pool):
                break
            starter = pool[i]
            starters.append({**starter, "slot": pos})
            bench_ids.add(starter["player_id"])

            # Flag close decisions (skip K — thin rosters make this noise)
            alt = pool[i + 1] if i + 1 < len(pool) else None
            if alt and pos != "K":
                margin = starter["adjusted_proj"] - alt["adjusted_proj"]
                if margin < CLOSE_DECISION_MARGIN:
                    close_decisions.append(_close_decision(pos, starter, alt, margin))

    # Fill FLEX with best remaining RB/WR/TE
    flex_pool = sorted(
        [
            p
            for pos in FLEX_POSITIONS
            for p in by_position.get(pos, [])
            if p["player_id"] not in bench_ids
        ],
        key=lambda x: x["adjusted_proj"],
        reverse=True,
    )
    for i in range(FLEX_COUNT):
        if i >= len(flex_pool):
            break
        flex_starter = flex_pool[i]
        starters.append({**flex_starter, "slot": "FLEX"})
        bench_ids.add(flex_starter["player_id"])

        alt = flex_pool[i + 1] if i + 1 < len(flex_pool) else None
        if alt:
            margin = flex_starter["adjusted_proj"] - alt["adjusted_proj"]
            if margin < CLOSE_DECISION_MARGIN:
                close_decisions.append(_close_decision("FLEX", flex_starter, alt, margin))

    # All remaining players go to bench
    all_players = [p for pos_list in by_position.values() for p in pos_list]
    bench = sorted(
        [p for p in all_players if p["player_id"] not in bench_ids],
        key=lambda x: x["adjusted_proj"],
        reverse=True,
    )

    logger.info(
        f"[Start/Sit] Week {week} — {len(starters)} starters, "
        f"{len(bench)} bench, {len(close_decisions)} close decisions"
    )

    return {
        "week": week,
        "season": season,
        "season_type": season_type,
        "starters": starters,
        "bench": bench,
        "close_decisions": close_decisions,
        "offseason_note": None,
        "warning": warning,
    }
