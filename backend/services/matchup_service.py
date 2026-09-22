"""
This week's matchups across every league: projected score vs the opponent, win
probability, lineup problems, and when your starters play.

The pure functions (win_probability, lineup_issues, kickoff_windows) take plain dicts and
are tested directly. The fetchers turn one Sleeper or ESPN league into the same shape:
{"you": [starter...], "bench": [...], "opp": [starter...], "opp_name", "record", "url"},
every player keyed by Sleeper id.
"""
import logging
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from services.recap_service import SLOT_ELIGIBLE

logger = logging.getLogger(__name__)

OUT = {"Out", "IR", "PUP", "Sus", "NFI"}     # won't play: projects zero
WARN = {"Questionable", "Doubtful"}          # might not play: flag, keep the projection
EASTERN = ZoneInfo("America/New_York")
# ponytail: fixed spread for weekly fantasy scores; fit it from real results once we
# store final scores, if the percentages feel off.
SCORE_SD = 25.0


def win_probability(you: float, opp: float) -> float:
    """Chance your projected total beats theirs, treating the margin as normal with a fixed spread."""
    return round(0.5 * (1 + math.erf((you - opp) / (SCORE_SD * math.sqrt(2)))), 3)


def playing(p: dict, schedule: dict) -> bool:
    """False when the player is ruled out or his team is on bye (schedule known and he's not in it)."""
    if p.get("injury_status") in OUT:
        return False
    return not schedule or p.get("nfl_team") in schedule


def team_score(starters: list[dict], schedule: dict) -> float:
    return round(sum((p.get("proj") or 0.0) for p in starters if playing(p, schedule)), 1)


def lineup_issues(league: dict, starters: list[dict], bench: list[dict], schedule: dict) -> list[dict]:
    """Problems you can act on in one lineup: a starter who won't play (out or on bye), an
    empty slot, or a starter who might not play. Each carries the best legal swap from the bench."""
    issues = []
    used = set()

    def best_swap(slot: str) -> dict | None:
        eligible = SLOT_ELIGIBLE.get(slot, set())
        pool = [b for b in bench if b["position"] in eligible and playing(b, schedule) and b["player_id"] not in used]
        pick = max(pool, key=lambda b: b.get("proj") or 0, default=None)
        if pick:
            used.add(pick["player_id"])
        return pick

    for p in starters:
        if not p.get("player_id"):
            reason, severity = f"Your {p['slot']} spot is empty", "out"
        elif p.get("injury_status") in OUT:
            reason, severity = f"{p['name']} is {p['injury_status']} and in your lineup", "out"
        elif schedule and p.get("nfl_team") not in schedule:
            reason, severity = f"{p['name']} is on bye and in your lineup", "out"
        elif p.get("injury_status") in WARN:
            reason, severity = f"{p['name']} is {p['injury_status']}", "warn"
        else:
            continue
        swap = best_swap(p["slot"]) if severity == "out" else None
        kickoff = (schedule.get(p.get("nfl_team")) or {}).get("kickoff")
        issues.append({
            "league_id": league["league_id"], "platform": league["platform"], "league_name": league["name"],
            "url": league.get("url"), "severity": severity, "title": reason,
            "slot": p["slot"], "player_id": p.get("player_id"),
            "swap": {"player_id": swap["player_id"], "name": swap["name"], "proj": swap.get("proj")} if swap else None,
            "kickoff": kickoff.isoformat() if kickoff else None,
        })
    return issues


def group_needs(issues: list[dict]) -> list[dict]:
    """Starters who won't play stay one per league (each is its own fix). A questionable
    player becomes one line listing every lineup he's in, instead of repeating."""
    out = [i for i in issues if i["severity"] == "out"]
    warns: dict[str, dict] = {}
    for i in issues:
        if i["severity"] != "warn":
            continue
        w = warns.setdefault(i["player_id"], {**i, "leagues": []})
        w["leagues"].append({"league_id": i["league_id"], "platform": i["platform"], "name": i["league_name"], "url": i["url"]})
    grouped = list(warns.values())
    for w in grouped:
        w["league_name"] = ", ".join(l["name"] for l in w["leagues"])
    out.sort(key=lambda i: i["kickoff"] or "")
    grouped.sort(key=lambda i: i["kickoff"] or "")
    return out + grouped


def _window_label(kickoff: datetime) -> str:
    """'Sun 1:00 PM' in Eastern time, how the NFL schedule is talked about."""
    et = kickoff.astimezone(EASTERN)
    return et.strftime("%a %-I:%M %p")


def kickoff_windows(starters: list[dict], schedule: dict) -> list[dict]:
    """Group your starters (each player once, however many lineups he's in) by kickoff time."""
    windows: dict[datetime, dict] = {}
    for p in starters:
        game = schedule.get(p.get("nfl_team"))
        if not game or not playing(p, schedule):
            continue
        w = windows.setdefault(game["kickoff"], {"kickoff": game["kickoff"], "state": game["state"], "players": {}})
        w["players"].setdefault(p["player_id"], p["name"])
    return [
        {"label": _window_label(k), "kickoff": k.isoformat(), "state": w["state"],
         "count": len(w["players"]), "players": sorted(w["players"].values())}
        for k, w in sorted(windows.items())
    ]


# ── Fetching one league into the shared shape ─────────────────────────────────

def _player(pid: str, slot: str, all_players: dict, proj: dict) -> dict:
    sp = all_players.get(pid) or {}
    name = sp.get("full_name") or f"{sp.get('first_name', '')} {sp.get('last_name', '')}".strip() or pid
    return {"player_id": pid, "name": name, "position": sp.get("position") or ("DEF" if pid.isalpha() else "?"),
            "nfl_team": sp.get("team") or (pid if pid.isalpha() else None),
            "injury_status": sp.get("injury_status") or "Active", "slot": slot, "proj": proj.get(pid)}


async def sleeper_matchup(league: dict, sleeper_user_id: str, week: int, all_players: dict, proj: dict) -> dict | None:
    from services import sleeper_service

    info, rosters, matchups, users = (
        await sleeper_service.get_league(league["league_id"]),
        await sleeper_service.get_league_rosters(league["league_id"]),
        await sleeper_service.get_matchups(league["league_id"], week, live=True),
        await sleeper_service.get_league_users(league["league_id"]),
    )
    mine = next((r for r in rosters if r.get("owner_id") == sleeper_user_id), None)
    if not mine:
        return None
    me = next((m for m in matchups if m.get("roster_id") == mine["roster_id"]), None)
    opp = next((m for m in matchups if me and m.get("matchup_id") == me.get("matchup_id")
                and m.get("roster_id") != mine["roster_id"]), None)
    slots = [s for s in (info or {}).get("roster_positions") or [] if s not in ("BN", "IR", "TAXI")]

    def lineup(entry):
        # Sleeper lists starters in slot order; "0" is an empty slot.
        return [(_player(pid, slot, all_players, proj) if pid and pid != "0"
                 else {"player_id": None, "name": None, "position": None, "slot": slot, "proj": 0})
                for pid, slot in zip((entry or {}).get("starters") or [], slots)]

    you = lineup(me or {"starters": mine.get("starters")})
    starter_ids = {p["player_id"] for p in you}
    bench = [_player(pid, "BN", all_players, proj) for pid in (mine.get("players") or [])
             if pid not in starter_ids and pid not in (mine.get("reserve") or [])]
    opp_roster = next((r for r in rosters if opp and r.get("roster_id") == opp.get("roster_id")), {})
    owner = next((u for u in users if u.get("user_id") == opp_roster.get("owner_id")), {})
    s = mine.get("settings") or {}
    return {
        "you": you, "bench": bench, "opp": lineup(opp) if opp else [],
        "opp_name": (owner.get("metadata") or {}).get("team_name") or owner.get("display_name") or "Opponent",
        "record": f"{s.get('wins', 0)}-{s.get('losses', 0)}" + (f"-{s['ties']}" if s.get("ties") else ""),
        "url": f"https://sleeper.com/leagues/{league['league_id']}/team",
    }


async def espn_matchup(league: dict, user, season: int, all_players: dict, proj: dict) -> dict | None:
    from services import espn_service

    data = await espn_service.get_espn_league(league["league_id"], season, user.espn_s2, user.swid)
    ul_team_id = league.get("team_id")
    me = espn_service.espn_my_team(data or {}, swid=user.swid, team_id=ul_team_id)
    if not me:
        return None
    period = (data.get("status") or {}).get("currentMatchupPeriod")
    game = next((g for g in data.get("schedule") or [] if g.get("matchupPeriodId") == period
                 and me["id"] in ((g.get("home") or {}).get("teamId"), (g.get("away") or {}).get("teamId"))), None)
    opp_id = None
    if game:
        opp_id = game["away"]["teamId"] if (game.get("home") or {}).get("teamId") == me["id"] else game["home"]["teamId"]
    opp_team = next((t for t in data.get("teams") or [] if t.get("id") == opp_id), None)

    def split(team):
        entries = (team.get("roster") or {}).get("entries") or []
        matched = espn_service.espn_to_sleeper_ids(entries, all_players)
        starters, bench = [], []
        for pid, e in matched:
            slot = espn_service.ESPN_TO_SLOT.get(e.get("lineupSlotId"))
            (starters if slot else bench).append(_player(pid, slot or "BN", all_players, proj))
        return starters, bench

    you, bench = split(me)
    rec = (me.get("record") or {}).get("overall") or {}
    return {
        "you": you, "bench": bench, "opp": split(opp_team)[0] if opp_team else [],
        "opp_name": (opp_team or {}).get("name") or "Opponent",
        "record": f"{rec.get('wins', 0)}-{rec.get('losses', 0)}" + (f"-{rec['ties']}" if rec.get("ties") else ""),
        "url": f"https://fantasy.espn.com/football/team?leagueId={league['league_id']}&teamId={me['id']}&seasonId={season}",
    }
