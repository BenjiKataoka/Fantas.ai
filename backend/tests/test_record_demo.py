"""record_demo's anonymizer: names replaced field by field, ids as text, leaks caught."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from record_demo import anonymize, find_leaks, real_leaks  # noqa: E402

raw = {
    "recorded_at": "2026-09-25T18:00:00+00:00",
    "me": {"email": "someone@example.com", "username": "someone", "sleeper_username": "realhandle",
           "primary_league": {"league_id": "3333333333", "platform": "ESPN"}},
    "leagues": [{"league_id": "1111111111111111111", "name": "Real League", "platform": "SLEEPER"},
                {"league_id": "3333333333", "name": "Other League", "platform": "ESPN"}],
    "entries": [
        {"method": "GET", "path": "/leagues", "params": {"sleeper_username": "realhandle"}, "status": 200,
         "body": {"leagues": [{"league_id": "1111111111111111111", "name": "Real League"}],
                  "sleeper_user_id": "222222222222222222"}},
        {"method": "GET", "path": "/matchups", "params": {"sleeper_username": "realhandle"}, "status": 200,
         "body": {"leagues": [{"league_id": "3333333333", "name": "Other League", "my_name": "My Real Team",
                               "opp_name": "Josh Allen", "opp_logo": "https://sleepercdn.com/avatars/x",
                               "my_logo": "https://sleepercdn.com/avatars/y",
                               "url": "https://fantasy.espn.com/football/team?leagueId=3333333333&teamId=3"}],
                  "needs": [{"league_name": "Real League, Other League", "title": "Nico Collins is Doubtful"}]}},
        {"method": "GET", "path": "/news", "params": {}, "status": 200,
         "body": {"news": [{"headline": "Josh Allen praises rookie", "player_name": "Puka Nacua"}]}},
        {"method": "GET", "path": "/tracker/roster-analysis", "params": {}, "status": 200,
         "body": {"running": True, "total": 2}},
        {"method": "GET", "path": "/results", "params": {"sleeper_username": "realhandle"}, "status": 200,
         "body": {"misses": [{"name": "Tre Tucker", "league_name": "Real League"}]}},
    ],
}

snap, names, teams, text = anonymize(raw)
by_path = {e["path"]: e for e in snap["entries"]}

m = by_path["/matchups"]["body"]["leagues"][0]
assert m["name"] == names["Other League"] != "Other League"
assert m["my_name"] == teams["My Real Team"] and m["opp_name"] == teams["Josh Allen"]
assert m["opp_logo"] is None and m["my_logo"] is None and m["url"] is None
assert m["league_id"] == text["3333333333"] != "3333333333"
assert by_path["/matchups"]["body"]["needs"][0]["league_name"] == f'{names["Real League"]}, {names["Other League"]}'
assert by_path["/matchups"]["params"]["sleeper_username"] == "demo_manager"
# Free text is never rewritten: a team named after a real player must not change the news.
assert by_path["/news"]["body"]["news"][0]["headline"] == "Josh Allen praises rookie"
# Player names stay; only the league name beside them changes.
assert by_path["/results"]["body"]["misses"][0] == {"name": "Tre Tucker", "league_name": names["Real League"]}
# A run caught mid-flight would make the demo poll forever.
assert by_path["/tracker/roster-analysis"]["body"]["running"] is False
me = by_path["/me"]["body"]
assert me["email"] is None and me["is_admin"] is False and me["sleeper_username"] == "demo_manager"
assert me["primary_league"]["league_id"] == text["3333333333"]
assert by_path["/leagues"]["body"]["sleeper_user_id"] != "222222222222222222"

# Leak finder: reports every hit with its path.
leaks = find_leaks(snap, [*names, *teams, *text, "someone@example.com"])
assert leaks == [("$.entries[2].body.news[0].headline", "Josh Allen")], leaks
# Only a team name inside news or video text is forgiven.
assert real_leaks(leaks, teams) == []
assert real_leaks([("$.entries[1].body.leagues[0].name", "Josh Allen")], teams) != []
assert find_leaks({"a": "mail me at x@y.com"}, []) == [("$.a", "x@y.com")]
assert find_leaks({"a": "Benji Kataoka"}, []) == [("$.a", "kataoka")]

print("record_demo: all assertions passed")
