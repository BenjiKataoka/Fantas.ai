"""GET /api/waivers: one league's best free agents and who each would replace.
POST /api/waivers/analyze/{player_id}: on-demand one-call AI verdict (Add / Stash / Pass)."""
import asyncio
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from config import GEMINI_PRIMARY
from database import get_db
from models.news import PlayerNews
from models.user import User
from services import espn_service, gemini_client, nfl_service, rotowire_service, sleeper_service, tracker_service
from services.projection_engine import this_week_projection, weights_from_user
from services.projection_service import _extract_sleeper_pts, get_nfl_state
from services.rule_filter_service import classify_news_type
from services.utils import normalize_name
from services.recap_service import best_lineup
from services.league_service import resolve_sleeper_user_id
from services.waiver_service import POSITIONS, rank_free_agents

router = APIRouter()


async def _none(value=None):
    """Placeholder for a gather slot that only applies to one platform."""
    return value
logger = logging.getLogger(__name__)

MIN_PROJ = 1.0      # below this a free agent isn't worth a roster spot unless he's trending
HORIZON = 4         # waiver pickups are judged on the next month, not one matchup
LAST_REG_WEEK = 18
OUT_LONG = {"IR", "PUP", "Sus", "NFI"}   # multi-week absences: zero for the whole horizon
OUT_WEEK = {"Out", "Doubtful"}          # zero this week only; the drop signal covers the rest
DROP_WARN_MIN = 5000                    # ignore drop counts too small to mean anything


async def _recent_news(db: AsyncSession, candidates: dict[str, str]) -> dict[str, list[dict]]:
    """Up to 3 newest headlines per candidate: stored news plus the live RotoWire and ESPN feeds,
    matched by normalized name. No AI involved."""
    by_name = {normalize_name(name): pid for pid, name in candidates.items()}
    rotowire, espn = await asyncio.gather(
        asyncio.to_thread(rotowire_service.scrape_rotowire_news),
        nfl_service.get_espn_news(),
        return_exceptions=True,
    )
    items = []
    for feed in (rotowire, espn):
        if isinstance(feed, Exception):
            logger.warning(f"[Waivers] news feed failed: {feed}")
            continue
        items += [(by_name[n], i) for i in feed if (n := normalize_name(i.get("player_name") or "")) in by_name]

    rows = (await db.execute(
        select(PlayerNews).where(PlayerNews.player_id.in_(list(candidates)))
    )).scalars().all()
    items += [(r.player_id, {"headline": r.headline, "news_body": r.news_body, "published_at": r.published_at,
                             "source_url": r.source_url, "news_type": r.news_type}) for r in rows]

    recent: dict[str, list[dict]] = {}
    for pid, i in items:
        lst = recent.setdefault(pid, [])
        if any(x["headline"] == i["headline"] for x in lst):
            continue
        lst.append({
            "headline": i["headline"],
            "published_at": i.get("published_at"),
            "source_url": i.get("source_url"),
            "news_type": i.get("news_type") or classify_news_type(i["headline"], i.get("news_body") or ""),
        })
    for lst in recent.values():
        lst.sort(key=lambda x: x["published_at"] or datetime.min, reverse=True)
        del lst[3:]
    return recent


async def _espn_context(league_id: str, user: User, season: int, db: AsyncSession, all_players: dict) -> dict:
    """The same three things the Sleeper path needs, from an ESPN league: who's taken
    league-wide, your own players, and the league's lineup slots."""
    from models.user import UserLeague

    team_id = (await db.execute(select(UserLeague.team_id).where(
        UserLeague.user_id == user.id, UserLeague.platform == "ESPN", UserLeague.league_id == league_id,
    ))).scalar_one_or_none()
    data = await espn_service.get_espn_league(league_id, season, user.espn_s2, user.swid)
    me = espn_service.espn_my_team(data or {}, swid=user.swid, team_id=team_id)
    if not me:
        raise HTTPException(status_code=404, detail="You don't have a team in this league.")
    taken = {pid for t in (data.get("teams") or [])
             for pid, _ in espn_service.espn_to_sleeper_ids((t.get("roster") or {}).get("entries") or [], all_players)}
    mine = espn_service.espn_to_sleeper_ids((me.get("roster") or {}).get("entries") or [], all_players)
    return {
        "taken": taken,
        # Everyone but IR counts as a player you could start.
        "my_ids": [pid for pid, e in mine if e.get("lineupSlotId") != 21],
        "slots": espn_service.espn_roster_positions(data or {}),
        "name": ((data or {}).get("settings") or {}).get("name"),
    }


async def _board(sleeper_username: str, league_id: str, user: User, db: AsyncSession,
                 platform: str = "SLEEPER") -> dict:
    """Ranked free agents plus the pieces the analyze prompt needs. Every upstream call is
    cached, so rebuilding this for one Analyze click is cheap."""
    state = await get_nfl_state()
    if state.get("season_type") == "off":
        raise HTTPException(status_code=400, detail="The waiver wire opens once the season does.")
    season, week = state["season"], state["week"]
    weeks = list(range(week, min(week + HORIZON, LAST_REG_WEEK + 1)))

    sleeper_user_id = await resolve_sleeper_user_id(user, sleeper_username)
    if platform == "SLEEPER" and not sleeper_user_id:
        raise HTTPException(status_code=404, detail=f"Sleeper user '{sleeper_username}' not found")

    league, rosters, all_players, (espn_by_id, espn_by_name), market, adds, drops, *sleeper_weeks = await asyncio.gather(
        sleeper_service.get_league(league_id) if platform == "SLEEPER" else _none(),
        sleeper_service.get_league_rosters(league_id) if platform == "SLEEPER" else _none([]),
        sleeper_service.get_all_players(),
        espn_service.get_espn_projections_full(season, week),
        espn_service.get_espn_market_pool(season, week),
        sleeper_service.get_trending_players("add", limit=100),
        sleeper_service.get_trending_players("drop", limit=100),
        *(sleeper_service.get_projections(season, w) for w in weeks),
    )
    if platform == "ESPN":
        ctx = await _espn_context(league_id, user, season, db, all_players)
    else:
        mine = next((r for r in rosters if r.get("owner_id") == sleeper_user_id), None)
        if not mine:
            raise HTTPException(status_code=404, detail="You don't have a roster in this league.")
        benched = set(mine.get("reserve") or []) | set(mine.get("taxi") or [])
        ctx = {
            "taken": {pid for r in rosters for key in ("players", "reserve", "taxi") for pid in (r.get(key) or [])},
            "my_ids": [pid for pid in (mine.get("players") or []) if pid not in benched],
            "slots": (league or {}).get("roster_positions") or [],
            "name": (league or {}).get("name"),
        }
    taken = ctx["taken"]
    add_counts = {t["player_id"]: t.get("count") or 0 for t in adds}
    drop_counts = {t["player_id"]: t.get("count") or 0 for t in drops}
    weights = weights_from_user(user)

    def row(pid: str) -> dict | None:
        sp = all_players.get(pid) or {}
        if sp.get("position") not in POSITIONS:
            return None
        name = sp.get("full_name") or f"{sp.get('first_name', '')} {sp.get('last_name', '')}".strip()
        status = sp.get("injury_status")
        w = this_week_projection(sp, sleeper_weeks[0].get(pid), espn_by_id, espn_by_name, weights)
        # Sleeper keeps projecting injured players, so availability overrides the numbers.
        # ESPN only projects the current week; later weeks are Sleeper's.
        per_week = [w["weighted_proj"] or 0.0] + [_extract_sleeper_pts(p.get(pid)) or 0.0 for p in sleeper_weeks[1:]]
        if status in OUT_LONG:
            per_week = [0.0] * len(per_week)
        elif status in OUT_WEEK:
            per_week[0] = 0.0
        n_add, n_drop = add_counts.get(pid, 0), drop_counts.get(pid, 0)
        return {
            "player_id": pid, "name": name, "position": sp["position"], "nfl_team": sp.get("team"),
            "injury_status": status or "Active", "injury_body_part": sp.get("injury_body_part"),
            "week_proj": round(per_week[0], 2),
            "proj": round(sum(per_week) / len(per_week), 2),  # what the ranking and "replaces" use
            "confidence_flag": w["confidence_flag"],
            "percent_rostered": (market.get(normalize_name(name)) or {}).get("percent_rostered"),
            "adds": n_add, "drops": n_drop,
            "being_dropped": n_drop >= DROP_WARN_MIN and n_drop > n_add,
        }

    pool = {pid for pid, s in sleeper_weeks[0].items() if (_extract_sleeper_pts(s) or 0) >= MIN_PROJ} | set(add_counts)
    free_agents = [r for pid in pool - taken if (r := row(pid))]
    my_rows = [r for pid in ctx["my_ids"] if (r := row(pid))]

    candidates = rank_free_agents(free_agents, my_rows, ctx["slots"])
    news = await _recent_news(db, {c["player_id"]: c["name"] for c in candidates})
    for c in candidates:
        c["news"] = (news.get(c["player_id"]) or [None])[0]

    out = {
        "league_name": ctx["name"],
        "season": season,
        "week": week,
        "horizon_weeks": weeks,
        "candidates": candidates,
        # Your projected starters over the same horizon: the bar a pickup has to clear.
        "lineup": [{"slot": p["slot"], "name": p["name"], "position": p["position"], "proj": p["proj"]}
                   for p in best_lineup(my_rows, ctx["slots"], lambda r: r["proj"] or 0.0)],
    }
    if not espn_by_id:
        out["warning"] = "ESPN projections are unavailable right now, so these use Sleeper alone."
    return {"public": out, "my_rows": my_rows, "news": news}


@router.get("/waivers")
async def get_waivers(
    sleeper_username: str | None = Query(None, description="Sleeper username; not needed for ESPN leagues"),
    league_id: str = Query(..., description="League ID on its platform"),
    platform: str = Query("SLEEPER", pattern="^(SLEEPER|ESPN)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return (await _board(sleeper_username, league_id, user, db, platform))["public"]


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
    board = await _board(sleeper_username, league_id, user, db, platform)
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
