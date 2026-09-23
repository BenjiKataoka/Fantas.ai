"""GET /api/tape: a week of NFL highlights, filtered to the players you own.

Grouped by player rather than by video, because the page ranks by your stake: the guy
starting in three of your lineups comes before the one on a bench.
"""
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.player import Player
from models.roster import MyRoster
from models.user import User, UserLeague
from services import nfl_service, youtube_service as yt
from services.projection_service import get_nfl_state
from services.utils import normalize_name

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_LAG_DAYS = 2  # highlights land within a day or two of the final whistle


async def _week_window(season: int, week: int) -> tuple[str | None, str | None]:
    """ISO dates bounding a week's uploads, taken from the real kickoff times.

    Titles usually carry "| Week N", but some never do, so this window is what places
    those. Deriving it from the calendar was wrong by a week: on a Wednesday, the current
    week has not kicked off yet, so this week's Monday still belongs to the week before.
    """
    try:
        schedule = await nfl_service.get_week_schedule(season, week)
        kickoffs = sorted(v["kickoff"].date() for v in schedule.values() if v.get("kickoff"))
        if kickoffs:
            return str(kickoffs[0]), str(kickoffs[-1] + timedelta(days=UPLOAD_LAG_DAYS))
    except Exception as e:
        logger.warning(f"[Tape] schedule lookup failed for week {week}: {e}")
    # No schedule: fall back to the week in the title alone rather than a wrong window.
    return None, None


@router.get("/tape")
async def get_tape(
    week: int | None = Query(None, description="Defaults to the last completed week"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    state = await get_nfl_state()
    current = state.get("week") or 1
    # Default to last week: this week's highlights don't exist until games are played.
    week = week or max(1, current - 1)

    rows = (await db.execute(
        select(Player.player_id, Player.name, Player.position, Player.nfl_team,
               MyRoster.is_starter, UserLeague.league_name)
        .join(MyRoster, MyRoster.player_id == Player.player_id)
        .join(UserLeague, UserLeague.id == MyRoster.user_league_id)
        .where(MyRoster.user_id == user.id)
    )).all()

    # One entry per player, carrying every league he is on: a player rostered twice has
    # two rows here, and the page needs him once.
    players: dict[str, dict] = {}
    for pid, name, pos, team, starter, league in rows:
        p = players.setdefault(pid, {
            "player_id": pid, "name": name, "position": pos, "nfl_team": team,
            "held": 0, "starting": 0, "leagues": [], "videos": [],
        })
        p["held"] += 1
        p["starting"] += 1 if starter else 0
        if league and league not in p["leagues"]:
            p["leagues"].append(league)

    if not players:
        return {"week": week, "season": state.get("season"), "players": [], "games": [],
                "compilations": [], "roster_size": 0, "enabled": bool(yt.YOUTUBE_API_KEY)}

    since, until = await _week_window(state.get("season"), week)
    roster = {normalize_name(p["name"]): pid for pid, p in players.items()}
    found = await yt.highlights_for(roster, week=week, since=since, until=until)

    for kind in ("reels", "plays"):
        for v in found[kind]:
            for pid in v["player_ids"]:
                players[pid]["videos"].append({
                    "video_id": v["video_id"], "title": v["title"],
                    "thumbnail": v["thumbnail"], "published_at": v["published_at"],
                    "kind": "reel" if kind == "reels" else "play",
                    "opponent": v.get("opponent"),
                })

    # A player's own reel outranks a one-play clip, then newest first.
    for p in players.values():
        p["videos"].sort(key=lambda v: (v["kind"] != "reel", v["published_at"] or ""), reverse=False)

    # Only games one of your players was in, tagged with who.
    teams = {p["nfl_team"] for p in players.values() if p["nfl_team"]}
    games = []
    for g in found["games"]:
        abbrs = [a for t in g.get("teams", []) if (a := yt.team_abbr(t))]
        mine = sorted({p["name"] for p in players.values() if p["nfl_team"] in abbrs})
        if not mine:
            continue
        games.append({"video_id": g["video_id"], "title": g["title"],
                      "thumbnail": g["thumbnail"], "teams": g.get("teams", []),
                      "abbrs": abbrs, "players": mine})

    # Which of these will actually play on our page, and which must open on YouTube.
    shown = ([v["video_id"] for p in players.values() for v in p["videos"]]
             + [g["video_id"] for g in games] + [c["video_id"] for c in found["compilations"]])
    playable = await yt.playable_in_embed(shown)
    for p in players.values():
        for v in p["videos"]:
            v["playable"] = playable.get(v["video_id"], False)
    for v in games + found["compilations"]:
        v["playable"] = playable.get(v["video_id"], False)

    with_video = [p for p in players.values() if p["videos"]]
    # Rank by stake: lineups he started in, then teams he is on, then how much tape.
    with_video.sort(key=lambda p: (p["starting"], p["held"], len(p["videos"])), reverse=True)

    return {
        "week": week,
        "season": state.get("season"),
        "current_week": current,
        "players": with_video,
        "games": games,
        "compilations": found["compilations"],
        "roster_size": len(players),
        "enabled": bool(yt.YOUTUBE_API_KEY),
    }
