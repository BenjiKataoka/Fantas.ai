"""
Tests for rotowire_service.py
Covers: HTML parsing, cache behavior, 403 retry, ANALYSIS section exclusion, failure modes.
Usage: python3 tests/test_rotowire_service.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
from datetime import datetime


# ── Minimal realistic RotoWire HTML fixture ────────────────────────────────────
SAMPLE_HTML = """
<html><body>
<div class="news-update">
  <a class="news-update__player-link" href="/football/player-news/12345/">Patrick Mahomes</a>
  <h4 class="news-update__headline">Mahomes listed as questionable with ankle injury</h4>
  <p class="news-update__news">Mahomes was limited in practice Wednesday with an ankle issue. He is expected to play Sunday barring setbacks.</p>
  <p class="analysis">ANALYSIS: This is a minor concern...</p>
  <a href="/football/news/id/99999/">Source</a>
  <time datetime="2026-04-08T14:30:00">2h ago</time>
</div>
<div class="news-update">
  <a class="news-update__player-link" href="/football/player-news/67890/">Tyreek Hill</a>
  <h4 class="news-update__headline">Hill fully practiced Thursday</h4>
  <p class="news-update__news">Hill has no injury designation heading into Sunday's game.</p>
  <a href="/football/news/id/88888/">Source</a>
  <time datetime="2026-04-08T10:00:00">6h ago</time>
</div>
<div class="news-update">
  <!-- Block with no player name, should be skipped -->
  <h4 class="news-update__headline">Some headline with no player</h4>
  <p class="news-update__news">Some body text.</p>
</div>
</body></html>
"""

SAMPLE_HTML_NO_BLOCKS = "<html><body><p>No news today.</p></body></html>"


def run_parser_tests():
    from services.rotowire_service import _parse_news_page, _parse_timestamp

    print("=" * 50)
    print("ROTOWIRE SERVICE, PARSER UNIT TESTS")
    print("=" * 50)

    # [1] Parses two valid blocks, skips the one with no player name
    print("\n[1] Parses valid news blocks, skips no-player block...")
    items = _parse_news_page(SAMPLE_HTML)
    assert len(items) == 2, f"Expected 2 items, got {len(items)}"
    assert items[0]["player_name"] == "Patrick Mahomes"
    assert items[1]["player_name"] == "Tyreek Hill"
    print(f"    PASS, parsed {len(items)} items")

    # [2] Headline populated correctly
    print("\n[2] Headline parsed correctly...")
    assert "questionable" in items[0]["headline"].lower()
    print(f"    PASS, headline: '{items[0]['headline']}'")

    # [3] ANALYSIS section is NOT included in news_body
    print("\n[3] Paywalled ANALYSIS section excluded from news_body...")
    assert items[0]["news_body"] is not None
    assert "ANALYSIS" not in (items[0]["news_body"] or "").upper(), \
        f"ANALYSIS section leaked into news_body: {items[0]['news_body']}"
    print(f"    PASS, news_body clean: '{items[0]['news_body'][:60]}...'")

    # [4] Source URL constructed correctly
    print("\n[4] Source URL extracted...")
    assert items[0]["source_url"] is not None
    assert "rotowire.com" in items[0]["source_url"]
    print(f"    PASS, source_url: {items[0]['source_url']}")

    # [5] Timestamp parsed from datetime attribute
    print("\n[5] Timestamp parsed from <time datetime='...'>...")
    assert items[0]["published_at"] is not None
    assert isinstance(items[0]["published_at"], datetime)
    print(f"    PASS, published_at: {items[0]['published_at']}")

    # [6] Source field is ROTOWIRE
    print("\n[6] Source field is 'ROTOWIRE'...")
    assert items[0]["source"] == "ROTOWIRE"
    print(f"    PASS, source: {items[0]['source']}")

    # [7] Empty page returns empty list
    print("\n[7] Page with no news blocks returns empty list...")
    empty = _parse_news_page(SAMPLE_HTML_NO_BLOCKS)
    assert empty == [], f"Expected [], got {empty}"
    print(f"    PASS, empty list returned")

    # [8] _parse_timestamp handles relative "2h ago"
    print("\n[8] _parse_timestamp handles '2h ago' text fallback...")
    fake_el = MagicMock()
    fake_el.get.return_value = ""  # no datetime attribute
    fake_el.get_text.return_value = "2h ago"
    result = _parse_timestamp(fake_el)
    assert result is not None
    assert abs((datetime.utcnow() - result).total_seconds() - 7200) < 5
    print(f"    PASS, parsed as ~2h ago: {result}")

    # [9] _parse_timestamp returns None for None input
    print("\n[9] _parse_timestamp returns None for None input...")
    assert _parse_timestamp(None) is None
    print(f"    PASS")

    print("\n✅ All parser tests passed.")


def run_cache_tests():
    from services import rotowire_service

    print("\n" + "=" * 50)
    print("ROTOWIRE SERVICE, CACHE TESTS")
    print("=" * 50)

    import time

    # [1] Cache stores result and second call is instant
    print("\n[1] Cache hit returns result without re-scraping...")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = SAMPLE_HTML
    mock_response.raise_for_status = MagicMock()

    call_count = {"n": 0}
    def mock_get(*args, **kwargs):
        call_count["n"] += 1
        return mock_response

    # Clear cache before test
    rotowire_service._cache["data"] = None
    rotowire_service._cache["expires_at"] = None

    with patch("services.rotowire_service.requests.get", side_effect=mock_get):
        result1 = rotowire_service.scrape_rotowire_news(force_refresh=True)
        result2 = rotowire_service.scrape_rotowire_news(force_refresh=False)

    assert call_count["n"] == 1, f"Expected 1 HTTP call, got {call_count['n']} (cache not working)"
    assert len(result1) == len(result2) == 2
    print(f"    PASS, 1 HTTP call, cache returned same {len(result2)} items")

    # [2] force_refresh bypasses cache
    print("\n[2] force_refresh=True bypasses cache and re-scrapes...")
    with patch("services.rotowire_service.requests.get", side_effect=mock_get):
        rotowire_service.scrape_rotowire_news(force_refresh=True)

    assert call_count["n"] == 2, f"Expected 2 total HTTP calls after force_refresh, got {call_count['n']}"
    print(f"    PASS, force_refresh triggered re-scrape")

    print("\n✅ All cache tests passed.")


def run_failure_mode_tests():
    from services import rotowire_service

    print("\n" + "=" * 50)
    print("ROTOWIRE SERVICE, FAILURE MODE TESTS")
    print("=" * 50)

    # Reset cache before each test
    def reset_cache():
        rotowire_service._cache["data"] = None
        rotowire_service._cache["expires_at"] = None

    # [1] 403 response → retries 3 times, returns empty list (not an exception)
    print("\n[1] 403 response retries then returns []...")
    mock_403 = MagicMock()
    mock_403.status_code = 403
    mock_403.raise_for_status = MagicMock()

    call_count = {"n": 0}
    def mock_403_get(*args, **kwargs):
        call_count["n"] += 1
        return mock_403

    reset_cache()
    with patch("services.rotowire_service.requests.get", side_effect=mock_403_get), \
         patch("services.rotowire_service.time.sleep"):  # skip actual sleep
        result = rotowire_service.scrape_rotowire_news(force_refresh=True)

    assert result == [], f"Expected [] on 403, got {result}"
    assert call_count["n"] == 3, f"Expected 3 retry attempts, got {call_count['n']}"
    print(f"    PASS, 3 retries, returned []")

    # [2] Network exception → returns [] without raising
    print("\n[2] Network exception returns [] without raising...")
    reset_cache()
    with patch("services.rotowire_service.requests.get", side_effect=Exception("Connection refused")), \
         patch("services.rotowire_service.time.sleep"):
        result = rotowire_service.scrape_rotowire_news(force_refresh=True)

    assert result == [], f"Expected [] on network error, got {result}"
    print(f"    PASS, network error handled gracefully")

    # [3] Partial HTML (only one valid block) → returns what's parseable
    print("\n[3] Partial/malformed HTML returns what's parseable...")
    partial_html = """
    <html><body>
    <div class="news-update">
      <a class="news-update__player-link">Josh Allen</a>
      <h4 class="news-update__headline">Allen cleared to play</h4>
    </div>
    <div class="news-update">THIS IS GARBAGE</div>
    </body></html>
    """
    mock_partial = MagicMock()
    mock_partial.status_code = 200
    mock_partial.text = partial_html
    mock_partial.raise_for_status = MagicMock()

    reset_cache()
    with patch("services.rotowire_service.requests.get", return_value=mock_partial):
        result = rotowire_service.scrape_rotowire_news(force_refresh=True)

    assert len(result) == 1
    assert result[0]["player_name"] == "Josh Allen"
    print(f"    PASS, parsed 1 valid block, skipped garbage block")

    print("\n✅ All failure mode tests passed.")


if __name__ == "__main__":
    run_parser_tests()
    run_cache_tests()
    run_failure_mode_tests()
    print("\n" + "=" * 50)
    print("ALL ROTOWIRE TESTS PASSED ✅")
    print("=" * 50)
