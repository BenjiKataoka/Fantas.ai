"""Connected leagues: which one a request means, which ones a user has, and syncing their rosters."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import UserLeague
from services.espn_service import EspnAuthError

logger = logging.getLogger(__name__)


async def gather_per_league(leagues: list[dict], sleeper, espn, tag: str) -> list:
    """Run one call per league in parallel, dispatched on platform.

    Returns results positionally matching `leagues`: the call's value, the string
    "expired" when ESPN rejected the cookies, or None when the league failed. One
    league going down never takes the others with it, which is why every caller
    zips this back against `leagues` to build its own warnings.
    """
    async def one(league: dict):
        try:
            return await (espn(league) if league["platform"] == "ESPN" else sleeper(league))
        except EspnAuthError:
            return "expired"
        except Exception as e:
            logger.error(f"[{tag}] {league['platform']} {league['league_id']} failed: {e}")
            return None

    return await asyncio.gather(*(one(l) for l in leagues))


async def espn_team_ids(db: AsyncSession, user_id: int) -> dict[str, int]:
    """Your picked team id per public ESPN league, keyed by league_id. Public leagues
    find your team by the one you picked, not by SWID."""
    return dict((await db.execute(select(UserLeague.league_id, UserLeague.team_id).where(
        UserLeague.user_id == user_id, UserLeague.platform == "ESPN", UserLeague.team_id.isnot(None),
    ))).all())


async def espn_team_id(db: AsyncSession, user_id: int, league_id: str) -> Optional[int]:
    """The same, for one league. None when the team was never picked."""
    return (await db.execute(select(UserLeague.team_id).where(
        UserLeague.user_id == user_id, UserLeague.platform == "ESPN", UserLeague.league_id == league_id,
    ))).scalar_one_or_none()


async def get_or_create_user_league(db: AsyncSession, user_id: int, platform: str, league_id: str,
                                    **fields) -> UserLeague:
    """The user's row for this league, creating it if needed. Race-safe: two requests
    loading a new league at once (a double effect, portfolio + roster) both get the same
    row instead of one failing on the unique constraint. `fields` fill a new row only."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    await db.execute(
        pg_insert(UserLeague)
        .values(user_id=user_id, platform=platform, league_id=league_id, **fields)
        .on_conflict_do_nothing(constraint="uq_user_league")
    )
    return (await db.execute(select(UserLeague).where(
        UserLeague.user_id == user_id, UserLeague.platform == platform, UserLeague.league_id == league_id,
    ))).scalar_one()


async def resolve_user_league(db: AsyncSession, user_id: int, league_id: Optional[str]) -> Optional[UserLeague]:
    """The named league, or the user's primary (last loaded) one when no id is given."""
    q = select(UserLeague).where(UserLeague.user_id == user_id)
    q = q.where(UserLeague.league_id == league_id) if league_id else q.where(UserLeague.is_primary)
    # ponytail: league_id alone could match a Sleeper and an ESPN league with the same id;
    # add a platform param once ESPN leagues exist.
    return (await db.execute(q.limit(1))).scalar_one_or_none()


def league_season(nfl_state: dict) -> int:
    """
    The season whose Sleeper leagues we should look at.

    Sleeper always reports the upcoming season in `nfl_state` (e.g. 2026), but during
    the offseason those leagues don't exist yet, so fall back to the completed season.
    Both /api/leagues and /api/roster MUST use this so the dropdown and the roster
    validation agree on which season's leagues are eligible. Never hardcode the year.
    """
    season = nfl_state["season"]
    return season - 1 if nfl_state["season_type"] == "off" else season


async def espn_leagues(user, season: int, db: AsyncSession) -> list[dict]:
    """ESPN leagues for this user: every league their cookies unlock (filtered to redraft
    PPR like Sleeper's), plus public leagues they added by link without cookies."""
    from services import espn_service

    out: dict[str, dict] = {}
    if user.espn_s2 and user.swid:
        try:
            for l in await espn_service.get_espn_fan_leagues(user.espn_s2, user.swid, season):
                league = await espn_service.get_espn_league(l["league_id"], season, user.espn_s2, user.swid)
                if league and espn_service.espn_is_redraft_ppr(league):
                    out[l["league_id"]] = {"league_id": l["league_id"], "name": l["name"], "platform": "ESPN",
                                           "total_rosters": (league.get("settings") or {}).get("size"), "season": season}
        except espn_service.EspnAuthError:
            logger.warning(f"[Leagues] ESPN cookies expired for user {user.id}")
            user.espn_needs_reconnect = True
    public = (await db.execute(select(UserLeague).where(
        UserLeague.user_id == user.id, UserLeague.platform == "ESPN",
        UserLeague.team_id.isnot(None), UserLeague.season == season,
    ))).scalars().all()
    for ul in public:
        out.setdefault(ul.league_id, {"league_id": ul.league_id, "name": ul.league_name, "platform": "ESPN",
                                      "total_rosters": ul.total_rosters, "season": season, "public": True})
    return list(out.values())


RELEVANT_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


def full_name(player: dict) -> str:
    first = player.get("first_name", "")
    last = player.get("last_name", "")
    return f"{first} {last}".strip() or player.get("full_name", "Unknown")


def guess_slot(pid: str, starters: set, all_players: dict) -> str:
    """Best-effort slot label based on position for Sleeper rosters."""
    if pid not in starters:
        return "BN"
    return (all_players.get(pid) or {}).get("position", "BN")


async def _store_roster(db: AsyncSession, user, ul: UserLeague, player_ids: list[str],
                        starters: set[str], slots: dict[str, str], all_players: dict,
                        nfl_state: dict) -> dict:
    """Platform-neutral half of a sync. Takes Sleeper player ids (the app's canonical key),
    upserts them into players, replaces this league's my_roster rows, and saves this
    week's projections in-season. Doesn't commit."""
    from datetime import date

    from sqlalchemy import delete
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from models.player import Player
    from models.roster import MyRoster
    from services.espn_service import DEF_ESPN_ID
    from services.projection_engine import weights_from_user
    from services.projection_service import sync_projections
    from services.utils import normalize_name

    rows = []
    for pid in player_ids:
        p = all_players.get(pid, {})
        if p.get("position", "") not in RELEVANT_POSITIONS:
            continue
        # Sleeper returns espn_id as int, cast to str for VARCHAR column
        espn_id = str(p["espn_id"]) if p.get("espn_id") is not None else None
        if espn_id is None and p["position"] == "DEF":
            espn_id = DEF_ESPN_ID.get(pid)   # Sleeper leaves defenses blank, ESPN derives from the team
        rows.append({
            "player_id": pid, "name": full_name(p), "position": p["position"],
            "nfl_team": p.get("team") or p.get("nfl_team"), "sleeper_id": pid,
            "espn_id": espn_id, "espn_athlete_id": espn_id,
            "injury_status": p.get("injury_status", "Active"),
        })
    if rows:
        stmt = pg_insert(Player).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["player_id"],
            set_={k: stmt.excluded[k] for k in ("name", "position", "nfl_team", "espn_id", "injury_status")},
        )
        await db.execute(stmt)

    # Re-sync this league only; the user's other leagues keep their rows. The lock makes a
    # second sync of the same league wait for the first to commit instead of colliding on
    # my_roster's key (released at commit/rollback).
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": ul.id})
    await db.execute(delete(MyRoster).where(MyRoster.user_league_id == ul.id))
    for r in rows:
        db.add(MyRoster(
            user_league_id=ul.id, user_id=user.id, player_id=r["player_id"],
            is_starter=r["player_id"] in starters, slot=slots.get(r["player_id"], "BN"),
            acquisition_date=date.today(),
        ))

    projections: dict = {}
    if nfl_state["season_type"] in ("regular", "post") and rows:
        projections = await sync_projections(
            player_ids=[r["player_id"] for r in rows],
            espn_id_map={r["player_id"]: r["espn_id"] for r in rows if r["espn_id"]},
            name_map={r["player_id"]: normalize_name(r["name"]) for r in rows},
            season=nfl_state["season"],
            week=nfl_state["week"],
            db=db,
            weights=weights_from_user(user),
        )
    ul.synced_at = datetime.utcnow()
    return {"player_ids": player_ids, "starters": starters, "slots": slots,
            "all_players": all_players, "projections": projections}


async def sync_sleeper_league(db: AsyncSession, user, sleeper_user_id: str, ul: UserLeague,
                              nfl_state: dict, force: bool = False) -> Optional[dict]:
    """Pull one Sleeper league into Neon. Returns what the roster response needs, or None
    when the user has no team in the league. Doesn't commit or touch is_primary."""
    from services import sleeper_service

    roster = await sleeper_service.get_roster(ul.league_id, sleeper_user_id, force=force)
    if not roster:
        return None
    player_ids: list[str] = roster.get("players") or []
    starters: set[str] = set(roster.get("starters") or [])
    all_players = await sleeper_service.get_all_players()
    # Sleeper lists starters in the same order as the league's lineup slots, so pairing
    # them gives the real slot (SUPER_FLEX, FLEX) instead of just the position.
    lineup = [s for s in ((await sleeper_service.get_league(ul.league_id)) or {}).get("roster_positions") or []
              if s not in ("BN", "IR", "TAXI")]
    exact = dict(zip(roster.get("starters") or [], lineup)) if lineup else {}
    slots = {pid: exact.get(pid) or guess_slot(pid, starters, all_players) for pid in player_ids}
    return await _store_roster(db, user, ul, player_ids, starters, slots, all_players, nfl_state)


async def sync_espn_league(db: AsyncSession, user, ul: UserLeague, nfl_state: dict,
                           force: bool = False) -> Optional[dict]:
    """Pull one ESPN league into Neon: with the user's cookies (private leagues, team found
    by SWID) or without them (public leagues, team the user picked). ESPN players are
    mapped onto Sleeper ids so everything downstream (projections, lineup solver, stock
    profiles) works unchanged. Raises espn_service.EspnAuthError on expired cookies."""
    from services import espn_service, sleeper_service

    if ul.team_id is None and not (user.espn_s2 and user.swid):
        return None
    league = await espn_service.get_espn_league(ul.league_id, ul.season or nfl_state["season"],
                                                user.espn_s2, user.swid, force=force)
    team = espn_service.espn_my_team(league or {}, swid=user.swid, team_id=ul.team_id)
    if not team:
        return None
    all_players = await sleeper_service.get_all_players()
    matched = espn_service.espn_to_sleeper_ids((team.get("roster") or {}).get("entries") or [], all_players)
    slots = {pid: espn_service.ESPN_TO_SLOT.get(e.get("lineupSlotId"), "BN") for pid, e in matched}
    starters = {pid for pid, slot in slots.items() if slot != "BN"}
    result = await _store_roster(db, user, ul, [pid for pid, _ in matched], starters, slots,
                                 all_players, nfl_state)
    result["roster_positions"] = espn_service.espn_roster_positions(league)
    return result


async def sync_league(db: AsyncSession, user, ul: UserLeague, nfl_state: dict) -> Optional[dict]:
    """Dispatch on platform, for callers that loop over every league (the scheduler)."""
    if ul.platform == "ESPN":
        return await sync_espn_league(db, user, ul, nfl_state)
    if not user.sleeper_user_id:
        return None
    return await sync_sleeper_league(db, user, user.sleeper_user_id, ul, nfl_state)


async def resolve_sleeper_user_id(user, sleeper_username: Optional[str]) -> Optional[str]:
    """The Sleeper account for this request, or None for an ESPN-only user. Falls back to
    the id saved on the user so pages work without passing a username every time.

    `sleeper_username` arrives from the query string, so it is pinned to the account this
    login has already connected. It used to be trusted: one request naming someone else
    rebound your stored Sleeper identity and synced their roster into your dashboard.
    The first connection does the binding (nothing saved yet); DELETE /api/settings/sleeper
    is how you undo it.
    """
    from fastapi import HTTPException

    from services import sleeper_service

    if not sleeper_username:
        return user.sleeper_user_id
    resolved = await sleeper_service.get_user_id(sleeper_username)
    if user.sleeper_user_id and resolved and resolved != user.sleeper_user_id:
        raise HTTPException(
            status_code=403,
            detail="That Sleeper account isn't the one connected to your login. "
                   "Disconnect Sleeper in Settings first.",
        )
    return resolved


async def all_leagues(user, sleeper_user_id: Optional[str], season: int, db: AsyncSession) -> list[dict]:
    """Every eligible league across platforms: Sleeper (when the user has an account) plus ESPN."""
    from services import sleeper_service

    leagues = []
    if sleeper_user_id:
        leagues += [{**l, "platform": "SLEEPER"}
                    for l in await sleeper_service.get_eligible_leagues(sleeper_user_id, season=season)]
    return leagues + await espn_leagues(user, season, db)
