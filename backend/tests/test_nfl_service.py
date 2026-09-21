"""
Tests for nfl_service.py
Covers: get_teams_playing_today(), ESPN news parsing, failure modes, timestamp parsing.
Usage: python3 tests/test_nfl_service.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, AsyncMock, MagicMock


# ── ESPN scoreboard fixture ────────────────────────────────────────────────────
MOCK_SCOREBOARD = {
    "events": [
        {
            "competitions": [{
                "competitors": [
                    {"team": {"abbreviation": "KC"}},
                    {"team": {"abbreviation": "SF"}},
                ]
            }]
        },
        {
            "competitions": [{
                "competitors": [
                    {"team": {"abbreviation": "DAL"}},
                    {"team": {"abbreviation": "PHI"}},
                ]
            }]
        },
    ]
}

MOCK_SCOREBOARD_EMPTY = {"events": []}


# ── ESPN news fixture ──────────────────────────────────────────────────────────
MOCK_ESPN_NEWS = {
    "articles": [
        {
            "headline": "Mahomes clears concussion protocol",
            "description": "Patrick Mahomes has been cleared and is expected to start Sunday.",
            "published": "2026-04-08T14:00:00Z",
            "categories": [
                {"type": "athlete", "athleteName": "Patrick Mahomes", "athleteId": 3139477}
            ],
            "links": {"web": {"href": "https://espn.com/nfl/story/mahomes"}},
        },
        {
            # Article with no athlete category, should be skipped
            "headline": "NFL announces new overtime rules",
            "description": "League-wide rule change announced.",
            "published": "2026-04-08T12:00:00Z",
            "categories": [{"type": "league"}],
            "links": {},
        },
        {
            # Article with athlete but no headline, should be skipped
            "headline": "",
            "description": "Some update.",
            "published": "2026-04-08T11:00:00Z",
            "categories": [
                {"type": "athlete", "athleteName": "Josh Allen", "athleteId": 3918298}
            ],
            "links": {},
        },
    ]
}


def run_scoreboard_tests():
    from services import nfl_service

    print("=" * 50)
    print("NFL SERVICE, get_teams_playing_today() TESTS")
    print("=" * 50)

    async def _test():
        # Clear cache before each subtest
        nfl_service._cache.clear()

        # [1] Returns correct team abbreviations from scoreboard
        print("\n[1] Parses teams playing today from scoreboard...")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = MOCK_SCOREBOARD

        with patch("services.nfl_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            teams = await nfl_service.get_teams_playing_today(force_refresh=True)

        assert "KC" in teams
        assert "SF" in teams
        assert "DAL" in teams
        assert "PHI" in teams
        assert len(teams) == 4
        print(f"    PASS, teams: {sorted(teams)}")

        # [2] No games today → empty set (not an exception)
        print("\n[2] No games today → empty set...")
        nfl_service._cache.clear()
        mock_resp.json.return_value = MOCK_SCOREBOARD_EMPTY

        with patch("services.nfl_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            teams = await nfl_service.get_teams_playing_today(force_refresh=True)

        assert teams == set(), f"Expected empty set, got {teams}"
        print(f"    PASS, empty set returned")

        # [3] Network failure → empty set (not an exception)
        print("\n[3] Network failure returns empty set...")
        nfl_service._cache.clear()

        with patch("services.nfl_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("Connection timeout"))
            mock_client_cls.return_value = mock_client

            teams = await nfl_service.get_teams_playing_today(force_refresh=True)

        assert teams == set()
        print(f"    PASS, network error handled gracefully")

        # [4] Cache hit, second call doesn't re-fetch
        print("\n[4] Cache hit, second call skips HTTP...")
        nfl_service._cache.clear()
        call_count = {"n": 0}

        async def counting_get(*args, **kwargs):
            call_count["n"] += 1
            return mock_resp

        mock_resp.json.return_value = MOCK_SCOREBOARD

        with patch("services.nfl_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = counting_get
            mock_client_cls.return_value = mock_client

            await nfl_service.get_teams_playing_today(force_refresh=True)
            await nfl_service.get_teams_playing_today(force_refresh=False)

        assert call_count["n"] == 1, f"Expected 1 HTTP call, got {call_count['n']}"
        print(f"    PASS, only 1 HTTP call for 2 invocations")

        # [5] Abbreviations are uppercase
        print("\n[5] Team abbreviations are always uppercase...")
        nfl_service._cache.clear()
        lower_scoreboard = {
            "events": [{"competitions": [{"competitors": [{"team": {"abbreviation": "kc"}}]}]}]
        }
        mock_resp.json.return_value = lower_scoreboard

        with patch("services.nfl_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            teams = await nfl_service.get_teams_playing_today(force_refresh=True)

        assert "KC" in teams
        assert "kc" not in teams
        print(f"    PASS, lowercase abbreviation normalized to 'KC'")

    asyncio.run(_test())
    print("\n✅ All scoreboard tests passed.")


def run_news_parsing_tests():
    from services.nfl_service import _parse_espn_news, _parse_espn_timestamp
    from datetime import datetime

    print("\n" + "=" * 50)
    print("NFL SERVICE, ESPN NEWS PARSING TESTS")
    print("=" * 50)

    # [1] Parses player article, skips non-player and no-headline articles
    print("\n[1] Player articles parsed, non-player/empty skipped...")
    items = _parse_espn_news(MOCK_ESPN_NEWS)
    assert len(items) == 1, f"Expected 1 item (only Mahomes), got {len(items)}"
    assert items[0]["player_name"] == "Patrick Mahomes"
    assert items[0]["espn_athlete_id"] == "3139477"
    assert items[0]["source"] == "ESPN"
    print(f"    PASS, 1 item parsed: {items[0]['player_name']}")

    # [2] Headline and description populated
    print("\n[2] Headline and news_body populated...")
    assert items[0]["headline"] == "Mahomes clears concussion protocol"
    assert "cleared" in items[0]["news_body"]
    print(f"    PASS, headline: '{items[0]['headline']}'")

    # [3] Source URL extracted from web link
    print("\n[3] Source URL from web link...")
    assert items[0]["source_url"] == "https://espn.com/nfl/story/mahomes"
    print(f"    PASS, source_url: {items[0]['source_url']}")

    # [4] Timestamp parsed correctly
    print("\n[4] Timestamp parsed from ESPN ISO format...")
    assert items[0]["published_at"] is not None
    assert isinstance(items[0]["published_at"], datetime)
    print(f"    PASS, published_at: {items[0]['published_at']}")

    # [5] _parse_espn_timestamp edge cases
    print("\n[5] _parse_espn_timestamp handles various formats...")
    assert _parse_espn_timestamp("") is None
    assert _parse_espn_timestamp(None) is None
    assert _parse_espn_timestamp("2026-04-08T14:00:00Z") is not None
    print(f"    PASS, None/empty handled gracefully")

    # [6] Empty articles list returns empty list
    print("\n[6] Empty articles list returns []...")
    result = _parse_espn_news({"articles": []})
    assert result == []
    print(f"    PASS")

    # [7] news_body truncated at 2000 chars
    print("\n[7] news_body truncated at 2000 chars...")
    long_article = {
        "articles": [{
            "headline": "Long article",
            "description": "x" * 3000,
            "published": "2026-04-08T10:00:00Z",
            "categories": [{"type": "athlete", "athleteName": "Test Player", "athleteId": 1}],
            "links": {},
        }]
    }
    result = _parse_espn_news(long_article)
    assert len(result[0]["news_body"]) == 2000
    print(f"    PASS, body capped at 2000 chars")

    print("\n✅ All ESPN news parsing tests passed.")


def run_espn_news_failure_tests():
    from services import nfl_service

    print("\n" + "=" * 50)
    print("NFL SERVICE, ESPN NEWS FAILURE MODES")
    print("=" * 50)

    async def _test():
        nfl_service._cache.clear()

        # [1] ESPN news API failure returns [] not an exception
        print("\n[1] ESPN news API failure returns []...")
        with patch("services.nfl_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("ESPN is down"))
            mock_client_cls.return_value = mock_client

            result = await nfl_service.get_espn_news(force_refresh=True)

        assert result == [], f"Expected [], got {result}"
        print(f"    PASS, ESPN failure returns [] gracefully")

        # [2] ESPN transactions failure returns []
        print("\n[2] ESPN transactions failure returns []...")
        nfl_service._cache.clear()
        with patch("services.nfl_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("timeout"))
            mock_client_cls.return_value = mock_client

            result = await nfl_service.get_espn_transactions(force_refresh=True)

        assert result == []
        print(f"    PASS, transactions failure returns []")

    asyncio.run(_test())
    print("\n✅ All ESPN news failure mode tests passed.")


if __name__ == "__main__":
    run_scoreboard_tests()
    run_news_parsing_tests()
    run_espn_news_failure_tests()
    print("\n" + "=" * 50)
    print("ALL NFL SERVICE TESTS PASSED ✅")
    print("=" * 50)
