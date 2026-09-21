"""
Router tests for adding a public ESPN league by link (ESPN mocked, plus one live
private-league check). Usage: python3 tests/test_espn_public_leagues.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import AsyncMock, patch

from fastapi import Depends
from fastapi.testclient import TestClient

from auth import get_current_user
from database import get_db
from main import app
from models.user import User

LEAGUE = {
    "settings": {"name": "Public Test League", "size": 10,
                 "scoringSettings": {"scoringItems": [{"statId": 53, "points": 1.0}]},
                 "draftSettings": {"keeperCount": 0}},
    "teams": [{"id": 1, "name": "Alpha", "primaryOwner": "{A}"}, {"id": 2, "name": "Bravo", "primaryOwner": "{B}"}],
    "members": [{"id": "{A}", "displayName": "alice"}, {"id": "{B}", "displayName": "bob"}],
}


async def dev_user(db=Depends(get_db)):
    return await db.get(User, 1)


def run_tests():
    print("=" * 50); print("ESPN PUBLIC LEAGUES, ROUTER"); print("=" * 50)
    app.dependency_overrides[get_current_user] = dev_user
    with TestClient(app) as c:
        print("\n[1] Not a link → 400...")
        r = c.post("/api/leagues/espn/lookup", json={"league": "my league"})
        assert r.status_code == 400, r.text
        print("    PASS")

        print("\n[2] Live: a private league without cookies → clear 'private' message...")
        r = c.post("/api/leagues/espn/lookup", json={"league": "https://fantasy.espn.com/football/league?leagueId=1106982871"})
        assert r.status_code == 400 and "private" in r.json()["detail"], r.text
        print(f"    PASS, {r.json()['detail']}")

        with patch("services.espn_service.get_espn_league", new=AsyncMock(return_value=LEAGUE)):
            print("\n[3] Public league lookup lists teams with owners...")
            r = c.post("/api/leagues/espn/lookup", json={"league": "fantasy.espn.com/football/league?leagueId=424242"})
            d = r.json()
            assert r.status_code == 200 and d["name"] == "Public Test League", d
            assert d["teams"] == [{"team_id": 1, "name": "Alpha", "owner": "alice"},
                                  {"team_id": 2, "name": "Bravo", "owner": "bob"}], d["teams"]
            print("    PASS")

            print("\n[4] Connect with a team that isn't in the league → 400...")
            assert c.post("/api/leagues/espn/public", json={"league_id": "424242", "team_id": 9}).status_code == 400
            print("    PASS")

            print("\n[5] Connect, then it shows in /api/leagues as ESPN...")
            r = c.post("/api/leagues/espn/public", json={"league_id": "424242", "team_id": 2})
            assert r.status_code == 200, r.text
            with patch("services.espn_service.get_espn_fan_leagues", new=AsyncMock(return_value=[])):
                leagues = c.get("/api/leagues", params={"sleeper_username": "benjikataoka"}).json()["leagues"]
            mine = [l for l in leagues if l["league_id"] == "424242"]
            assert mine and mine[0]["platform"] == "ESPN" and mine[0]["public"], leagues
            print("    PASS")

        print("\n[6] Remove it...")
        assert c.delete("/api/leagues/espn/424242").status_code == 200
        with patch("services.espn_service.get_espn_fan_leagues", new=AsyncMock(return_value=[])):
            leagues = c.get("/api/leagues", params={"sleeper_username": "benjikataoka"}).json()["leagues"]
        assert not [l for l in leagues if l["league_id"] == "424242"]
        print("    PASS")


if __name__ == "__main__":
    run_tests()
    print("\nALL ESPN PUBLIC LEAGUE TESTS PASSED")
