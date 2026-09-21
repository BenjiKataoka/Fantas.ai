import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.player import Player
from models.roster import MyRoster
from services.league_service import resolve_user_league
from models.projection import Projection
from models.user import User
from auth import get_current_user
from services import espn_service, sleeper_service
from services.projection_service import get_nfl_state
from services.recap_service import SLOT_ELIGIBLE, best_lineup

router = APIRouter()
logger = logging.getLogger(__name__)

# Used only when the league's own slots can't be fetched.
DEFAULT_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K"]

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


async def _league_slots(ul, user) -> list[str]:
    """The league's lineup slots on its own platform; empty if they can't be fetched."""
    if not ul:
        return []
    if ul.platform == "ESPN":
        try:
            league = await espn_service.get_espn_league(ul.league_id, ul.season, user.espn_s2, user.swid)
        except espn_service.EspnAuthError:
            return []
        return espn_service.espn_roster_positions(league or {})
    return ((await sleeper_service.get_league(ul.league_id)) or {}).get("roster_positions") or []


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
        note = "Slim margin, monitor injury status closely before lock"
    else:
        note = "Slim margin, consider checking matchup before lock"
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
    league_id: str | None = Query(None, description="League to use; defaults to the last one loaded"),
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
    ul = await resolve_user_league(db, user.id, league_id)
    result = await db.execute(
        select(MyRoster, Player)
        .join(Player, MyRoster.player_id == Player.player_id)
        .where(MyRoster.user_league_id == (ul.id if ul else -1))
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

    players = [
        _build_player_dict(row.Player, proj_map.get(row.Player.player_id))
        for row in roster_rows
        if any(row.Player.position in eligible for eligible in SLOT_ELIGIBLE.values())
    ]

    # The league's real lineup (superflex, 3 WR, no kicker, ...), not a hardcoded one.
    slots = await _league_slots(ul, user) or DEFAULT_SLOTS

    starters = best_lineup(players, slots, lambda p: p["adjusted_proj"])
    starter_ids = {p["player_id"] for p in starters}
    bench = sorted((p for p in players if p["player_id"] not in starter_ids),
                   key=lambda x: x["adjusted_proj"], reverse=True)

    # A close call: the best bench player who could legally fill that slot is within the
    # margin. Kickers are skipped, thin K depth makes it noise.
    close_decisions: list[dict] = []
    for starter in starters:
        if starter["slot"] == "K":
            continue
        alt = next((b for b in bench if b["position"] in SLOT_ELIGIBLE[starter["slot"]]), None)
        if alt:
            margin = starter["adjusted_proj"] - alt["adjusted_proj"]
            if margin < CLOSE_DECISION_MARGIN:
                close_decisions.append(_close_decision(starter["slot"], starter, alt, margin))

    logger.info(
        f"[Start/Sit] Week {week}, {len(starters)} starters, "
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
