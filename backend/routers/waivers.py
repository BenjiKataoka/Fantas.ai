"""GET /api/waivers: one league's best free agents and who each would replace.
POST /api/waivers/analyze/{player_id}: on-demand one-call AI verdict (Add / Stash / Pass).

The board itself is built in services/waiver_service; this file is the HTTP surface
plus the analyze prompt and its per-user daily limit.
"""
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from config import GEMINI_PRIMARY
from database import get_db
from models.user import User
from services import gemini_client, tracker_service
from services.waiver_service import build_board

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/waivers")
async def get_waivers(
    sleeper_username: str | None = Query(None, description="Sleeper username; not needed for ESPN leagues"),
    league_id: str = Query(..., description="League ID on its platform"),
    platform: str = Query("SLEEPER", pattern="^(SLEEPER|ESPN)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return (await build_board(sleeper_username, league_id, user, db, platform))["public"]


# ponytail: in-memory cache and per-user counter, both reset on restart. Move to Neon if
# the app ever runs more than one backend process.
DAILY_ANALYZE_LIMIT = 20
VERDICTS = {"ADD", "STASH", "PASS"}
_verdicts: dict[tuple, dict] = {}                   # (date, user_id, league_id, player_id) → verdict
_user_calls: dict[tuple[str, int], int] = {}       # (date, user_id) → analyses today


def _fmt(v) -> str:
    return "n/a" if v is None else f"{v:.1f}"


def _analyze_prompt(c: dict, my_rows: list[dict], news: list[dict], profile: dict | None,
                    weeks: list[int]) -> str:
    starters_at_pos = sorted((r for r in my_rows if r["position"] == c["position"]),
                             key=lambda r: r["proj"] or 0, reverse=True)
    lines = [
        "You are a fantasy football analyst for a redraft PPR league. Decide whether the user "
        "should pick up this free agent.",
        "",
        f"PLAYER: {c['name']} ({c['position']}, {c['nfl_team'] or 'no team'})",
        f"Injury status: {c['injury_status']}" + (f" ({c['injury_body_part']})" if c.get("injury_body_part") else ""),
        f"Projected points this week: {_fmt(c['week_proj'])}",
        f"Average projected points per week, weeks {weeks[0]}-{weeks[-1]} (injured weeks count as 0): {_fmt(c['proj'])}",
        f"ESPN percent rostered: {c['percent_rostered'] if c['percent_rostered'] is not None else 'n/a'}",
        f"Sleeper adds last 24h: {c['adds']}, drops last 24h: {c['drops']}",
        "",
        "USER'S ROSTER AT THIS POSITION (avg projected points per week, same horizon):",
        *[f"- {r['name']}: {_fmt(r['proj'])} ({r['injury_status']})" for r in starters_at_pos],
        f"Projection model says he would replace: {c['replaces']['name']} (+{c['upgrade']:.1f}/wk)"
        if c.get("replaces") else "Projection model says he would not beat any current starter.",
        "",
        "RECENT NEWS (newest first):",
        *([f"- [{(n['published_at'].strftime('%b %d') if n['published_at'] else 'undated')}] {n['headline']}" for n in news]
          or ["- none found"]),
    ]
    if profile:
        lines += ["", "EXISTING ANALYST PROFILE:",
                  f"Concern level {profile.get('concern_level')}/10: {profile.get('concern_summary')}",
                  f"Bullish: {profile.get('bullish_factors')}", f"Bearish: {profile.get('bearish_factors')}"]
    lines += [
        "",
        "Weigh availability and role over raw projections: projections lag injuries and depth "
        "chart changes, and heavy drops usually mean bad news. Return JSON only:",
        '{"verdict": "ADD" | "STASH" | "PASS", "reasons": [2 or 3 strings, each ONE sentence under 20 words], '
        '"risk": "one sentence under 20 words on what could make this wrong"}',
        "Lead each reason with the deciding fact. If the news contradicts the injury status, trust the newer news.",
        "ADD = pick him up now, he helps soon. STASH = worth a bench spot for later value. PASS = not worth a spot.",
    ]
    return "\n".join(lines)


@router.post("/waivers/analyze/{player_id}")
async def analyze_free_agent(
    player_id: str,
    sleeper_username: str | None = Query(None, description="Sleeper username; not needed for ESPN leagues"),
    league_id: str = Query(..., description="League ID on its platform"),
    platform: str = Query("SLEEPER", pattern="^(SLEEPER|ESPN)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today().isoformat()
    remaining = DAILY_ANALYZE_LIMIT - _user_calls.get((today, user.id), 0)
    cached = _verdicts.get((today, user.id, league_id, player_id))
    if cached:
        return {**cached, "cached": True, "remaining": remaining}
    if remaining <= 0:
        raise HTTPException(status_code=429, detail=f"You've used all {DAILY_ANALYZE_LIMIT} analyses for today. They reset at midnight.")

    # Rebuilt server-side rather than trusting row data from the client: it goes into the prompt.
    board = await build_board(sleeper_username, league_id, user, db, platform)
    c = next((x for x in board["public"]["candidates"] if x["player_id"] == player_id), None)
    if not c:
        raise HTTPException(status_code=404, detail="That player isn't on this league's waiver wire.")
    profile = (await tracker_service.get_stock_profiles_for([player_id], db)).get(player_id)

    prompt = _analyze_prompt(c, board["my_rows"], board["news"].get(player_id) or [], profile,
                             board["public"]["horizon_weeks"])
    result = await gemini_client.call_json(prompt, GEMINI_PRIMARY, "Waivers")
    if not result or result.get("verdict") not in VERDICTS:
        raise HTTPException(status_code=503, detail="The AI analysis is unavailable right now. Try again later.")

    verdict = {
        "verdict": result["verdict"],
        "reasons": [str(r) for r in (result.get("reasons") or [])][:3],
        "risk": result.get("risk"),
    }
    _verdicts[(today, user.id, league_id, player_id)] = verdict
    _user_calls[(today, user.id)] = _user_calls.get((today, user.id), 0) + 1
    return {**verdict, "cached": False, "remaining": remaining - 1}
