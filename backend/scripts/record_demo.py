"""Record the public demo's snapshot: every request the frontend makes, answered by the
real API as Benji, then anonymized. Run from backend/ with the venv active:

    python3 scripts/record_demo.py

Writes frontend/src/demo/snapshot.json, or exits 1 without writing if a real name,
handle, id or email survived.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
OUT = BACKEND.parent / "frontend" / "src" / "demo" / "snapshot.json"

FAKE_LEAGUES = ["Sunday Scaries League", "Couch Coaches", "Waiver Wire Wednesday",
                "The Bye Week Club", "Gridiron Gossip", "Fourth and Long"]
FAKE_TEAMS = ["Gridiron Gurus", "Touchdown Tacos", "Blitz Brigade", "The Audibles",
              "Red Zone Regulars", "Hail Mary Heroes", "Pocket Passers", "End Zone Elite",
              "Two Minute Drill", "The Fumblers", "Play Action Pack", "Sack Masters",
              "Nickel Package", "Goal Line Stand", "Onside Kicks", "Victory Formation"]
DEMO_HANDLE = "demo_manager"
LEAGUE_URL = re.compile(r"sleeper\.com/leagues/|fantasy\.espn\.com/")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
FREE_TEXT = re.compile(r"\.(headline|news_body|title)$")


def build_maps(leagues: list[dict], team_names: set[str], handle: str,
               sleeper_user_id: str | None) -> tuple[dict, dict, dict]:
    names = {l["name"]: FAKE_LEAGUES[i % len(FAKE_LEAGUES)] for i, l in enumerate(leagues)}
    teams = {n: FAKE_TEAMS[i] if i < len(FAKE_TEAMS) else f"Team {i + 1}"
             for i, n in enumerate(sorted(team_names))}
    # Ids keep their length so nothing that measures or parses them notices.
    text = {str(l["league_id"]): str(10 ** (len(str(l["league_id"])) - 1) + i + 1)
            for i, l in enumerate(leagues)}
    if sleeper_user_id:
        text[str(sleeper_user_id)] = str(10 ** (len(str(sleeper_user_id)) - 1) + 99)
    if handle:
        text[handle] = DEMO_HANDLE
    return names, teams, text


def scrub(o, names: dict, teams: dict):
    """Replace names field by field. Free text (news, player names) is never touched:
    an opponent's team can be called "Josh Allen"."""
    if isinstance(o, dict):
        is_league = "league_id" in o
        out = {}
        for k, v in o.items():
            if k in ("my_name", "opp_name") and isinstance(v, str):
                out[k] = teams.get(v, v)
            elif k in ("my_logo", "opp_logo"):
                out[k] = None
            elif k == "url" and isinstance(v, str) and LEAGUE_URL.search(v):
                out[k] = None  # with a fake id it would open a missing league
            elif isinstance(v, str) and (k == "league_name" or (k == "name" and is_league)):
                # Grouped needs join league names with ", ".
                out[k] = ", ".join(names.get(part, part) for part in v.split(", "))
            elif k == "leagues" and isinstance(v, list) and all(isinstance(x, str) for x in v):
                out[k] = [names.get(x, x) for x in v]
            else:
                out[k] = scrub(v, names, teams)
        return out
    if isinstance(o, list):
        return [scrub(v, names, teams) for v in o]
    return o


def replace_text(s: str, text: dict) -> str:
    for old in sorted(text, key=len, reverse=True):
        s = re.sub(rf"(?<!\w){re.escape(old)}(?!\w)", text[old], s)
    return s


def anonymize(raw: dict) -> tuple[dict, dict, dict, dict]:
    me, entries = raw["me"], raw["entries"]
    team_names: set[str] = set()

    def collect(o) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("my_name", "opp_name") and isinstance(v, str):
                    team_names.add(v)
                else:
                    collect(v)
        elif isinstance(o, list):
            for v in o:
                collect(v)

    collect(entries)
    sleeper_uid = next((e["body"].get("sleeper_user_id") for e in entries
                        if e["path"] == "/leagues" and isinstance(e["body"], dict)), None)
    names, teams, text = build_maps(raw["leagues"], team_names, me.get("sleeper_username") or "", sleeper_uid)

    clean = [scrub(e, names, teams) for e in entries]
    for e in clean:
        if e["path"] == "/tracker/roster-analysis" and isinstance(e["body"], dict):
            e["body"]["running"] = False  # a run caught mid-flight would make the demo poll forever
    clean.append({"method": "GET", "path": "/me", "params": {}, "status": 200, "body": {
        "id": 1, "email": None, "username": "demo", "is_admin": False, "is_approved": True,
        "sleeper_username": me.get("sleeper_username"), "primary_league": me["primary_league"]}})

    dumped = json.dumps({"recorded_at": raw["recorded_at"], "entries": clean}, ensure_ascii=False)
    return json.loads(replace_text(dumped, text)), names, teams, text


def find_leaks(o, originals: list[str], path: str = "$") -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    if isinstance(o, dict):
        for k, v in o.items():
            hits += find_leaks(v, originals, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            hits += find_leaks(v, originals, f"{path}[{i}]")
    elif isinstance(o, str):
        hits += [(path, x) for x in originals if x in o]
        if "kataoka" in o.lower():
            hits.append((path, "kataoka"))
        hits += [(path, m) for m in EMAIL.findall(o)]
    return hits


def real_leaks(leaks: list[tuple[str, str]], teams: dict) -> list[tuple[str, str]]:
    # A team named after a real player ("Josh Allen") showing up in news about that player is not a leak.
    return [(p, w) for p, w in leaks if not (w in teams and FREE_TEXT.search(p))]


def record() -> dict:
    sys.path.insert(0, str(BACKEND))
    from fastapi import Depends
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    import config
    from auth import get_current_user
    from database import get_db
    from main import app
    from models.user import User

    admin_id = sorted(config.CLERK_ADMIN_IDS)[0]  # ponytail: first admin is Benji; add a --clerk-id flag if that changes

    async def as_admin(db=Depends(get_db)):
        return (await db.execute(select(User).where(User.clerk_id == admin_id))).scalar_one()

    app.dependency_overrides[get_current_user] = as_admin
    entries: list[dict] = []
    recorded_at = datetime.now(timezone.utc).isoformat()

    with TestClient(app) as c:
        def call(method: str, path: str, **params) -> dict:
            r = c.request(method, "/api" + path, params=params)
            if r.status_code >= 400:
                print(f"  {r.status_code} {method} {path} {params}")
            body = r.json()
            entries.append({"method": method, "path": path, "params": params, "status": r.status_code, "body": body})
            return body

        me = c.get("/api/me").json()
        handle = me["sleeper_username"]
        primary = me["primary_league"]
        u = {"sleeper_username": handle}

        call("GET", "/leagues")
        leagues = call("GET", "/leagues", **u)["leagues"]
        call("GET", "/matchups", **u)
        for _ in range(5):  # the first call can sync stale leagues behind the response
            if not call("GET", "/portfolio", **u).get("syncing"):
                break
            time.sleep(6)
        call("GET", "/results", **u)
        for path in ("/news", "/tracker", "/tracker/roster-analysis", "/settings", "/settings/espn"):
            call("GET", path)

        # Loading a roster makes that league the user's primary, so the real one goes last.
        player_ids: set[str] = set()
        for lg in sorted(leagues, key=lambda l: l["league_id"] == primary["league_id"]):
            lp = {**u, "league_id": lg["league_id"], "platform": lg["platform"]}
            roster = call("GET", "/roster", **lp)
            player_ids |= {p["player_id"] for p in roster.get("roster", [])}
            call("GET", f"/startsit/{roster['week']}", league_id=lg["league_id"])
            for w in range(1, roster["last_complete_week"] + 1):
                call("GET", f"/recap/{w}", **lp)
            call("GET", "/waivers", **lp)

        board = next(e["body"] for e in reversed(entries)
                     if e["path"] == "/waivers" and e["params"]["league_id"] == primary["league_id"])
        for cand in board.get("candidates", [])[:5]:
            call("POST", f"/waivers/analyze/{cand['player_id']}",
                 **u, league_id=primary["league_id"], platform=primary["platform"])

        for pid in sorted(player_ids):
            for rng in ("1w", "1m", "season"):
                call("GET", f"/tracker/{pid}/sentiment-history", range=rng)

        tape = call("GET", "/tape")
        for w in range(1, tape.get("current_week", 1)):
            call("GET", "/tape", week=w)

    app.dependency_overrides.clear()
    return {"recorded_at": recorded_at, "me": me, "leagues": leagues, "entries": entries}


def main() -> int:
    raw = record()
    snap, names, teams, text = anonymize(raw)
    originals = [o for o in (*names, *teams, *text, raw["me"].get("email"), raw["me"].get("username")) if o]
    leaks = real_leaks(find_leaks(snap, originals), teams)
    if leaks:
        for path, what in leaks[:40]:
            print(f"LEAK {path}: {what!r}")
        print(f"{len(leaks)} leak(s); snapshot NOT written.")
        return 1
    OUT.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(snap['entries'])} responses)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
