"""
Tests for the RSS news source (Phase 5+).
Covers: name matching + scoping, HTML/body handling, published parsing, the min-length
name filter, empty-scope short-circuit, per-feed failure isolation, and caching.
Network + feedparser are mocked — no real feeds are hit.
Usage: python3 tests/test_rss_service.py
"""
import asyncio
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import rss_service


def _entry(title, summary="", link="https://ex.com/a", published=(2026, 9, 18, 14, 30, 0, 0, 0, 0)):
    return SimpleNamespace(title=title, summary=summary, link=link, published_parsed=published)


def run_helper_tests():
    print("=" * 50); print("RSS — HELPERS"); print("=" * 50)

    assert rss_service._strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    print("    PASS — strip_html")

    dt = rss_service._parse_published(_entry("x"))
    assert dt == datetime(2026, 9, 18, 14, 30, 0), dt
    assert rss_service._parse_published(SimpleNamespace()) is None
    print("    PASS — parse_published (struct + missing)")

    # min-length filter drops "Ja"; dedups; keeps punctuated names normalized
    m = dict(rss_service._build_matcher(["Nico Collins", "Ja", "A.J. Brown", "Nico Collins"]))
    assert m == {"nico collins": "Nico Collins", "aj brown": "A.J. Brown"}, m
    print("    PASS — build_matcher (min-len + dedup)")
    print("✅ helpers ok")


def run_match_tests():
    print("\n" + "=" * 50); print("RSS — MATCH + SCOPE"); print("=" * 50)

    feed = [
        ("PFT",   _entry("Nico Collins (hamstring) uncertain for Week 2", "<p>The Texans WR is banged up.</p>", "https://pft.com/1")),
        ("ESPN",  _entry("Some other player scores twice", "Unrelated body", "https://espn.com/2")),
        ("CBS",   _entry("Report: CeeDee Lamb signs extension", "x" * 5000, "https://cbs.com/3")),
        ("YAHOO", _entry("Nico Collins expected to play", "back at practice", link=None)),  # no link → dropped
    ]

    async def _test():
        with patch.object(rss_service, "_fetch_feed", new=AsyncMock(return_value=feed)):
            # one _fetch_feed mock returns the whole set once; force_refresh bypasses cache
            with patch.object(rss_service, "FEEDS", [("X", "http://x")]):
                items = await rss_service.fetch_rss_news(["Nico Collins", "CeeDee Lamb"], force_refresh=True)

        by_url = {i["source_url"]: i for i in items}
        # Matched: Nico (PFT) + CeeDee (CBS). Dropped: unrelated (ESPN) + no-link (YAHOO).
        assert set(by_url) == {"https://pft.com/1", "https://cbs.com/3"}, by_url.keys()

        nico = by_url["https://pft.com/1"]
        assert nico["player_name"] == "Nico Collins"
        assert nico["source"] == "PFT"
        assert nico["news_body"] == "The Texans WR is banged up."      # HTML stripped
        assert nico["published_at"] == datetime(2026, 9, 18, 14, 30, 0)
        print("    PASS — matched Nico, correct fields + HTML strip")

        lamb = by_url["https://cbs.com/3"]
        assert len(lamb["news_body"]) == rss_service._MAX_BODY            # body truncated
        print("    PASS — matched CeeDee, body truncated to cap")
        print(f"    (unrelated + no-link items dropped: {len(feed)} in → {len(items)} out)")

    asyncio.run(_test())
    print("✅ match + scope ok")


def run_edgecase_tests():
    print("\n" + "=" * 50); print("RSS — EMPTY SCOPE / FAILURE / CACHE"); print("=" * 50)

    async def _empty():
        spy = AsyncMock(return_value=[])
        with patch.object(rss_service, "_fetch_feed", new=spy):
            out = await rss_service.fetch_rss_news([], force_refresh=True)
        assert out == [] and spy.await_count == 0, (out, spy.await_count)
        print("    PASS — empty scope short-circuits (no network)")
    asyncio.run(_empty())

    async def _isolation():
        # One feed raises inside _fetch_feed → it returns [] (caught internally); others survive.
        async def side_effect(client, source, url):
            if source == "PFT":
                raise RuntimeError("feed down")  # exercised via the real _fetch_feed below
            return [(source, _entry("Nico Collins update", "ok", f"https://{source}.com/1"))]

        # Use the REAL _fetch_feed so its try/except is what isolates the failure.
        class FakeResp:
            content = b""
            def raise_for_status(self): pass
        class FakeClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, **kw):
                if "profootballtalk" in url: raise RuntimeError("PFT down")
                return FakeResp()
        def fake_parse(content):
            return SimpleNamespace(entries=[_entry("Nico Collins update", "ok", "https://x.com/1")])

        with patch.object(rss_service.httpx, "AsyncClient", return_value=FakeClient()), \
             patch.object(rss_service.feedparser, "parse", side_effect=fake_parse):
            out = await rss_service.fetch_rss_news(["Nico Collins"], force_refresh=True)
        # PFT failed but the other 3 feeds still produced matched items.
        assert len(out) >= 1, out
        assert all(i["player_name"] == "Nico Collins" for i in out)
        print(f"    PASS — dead feed isolated, {len(out)} items from surviving feeds")
    asyncio.run(_isolation())

    async def _cache():
        rss_service._cache["data"] = None
        rss_service._cache["expires_at"] = None
        spy = AsyncMock(return_value=[("PFT", _entry("Nico Collins hurt", "x", "https://pft.com/9"))])
        with patch.object(rss_service, "_fetch_feed", new=spy), \
             patch.object(rss_service, "FEEDS", [("PFT", "http://pft")]):
            a = await rss_service.fetch_rss_news(["Nico Collins"], force_refresh=True)   # populates cache
            b = await rss_service.fetch_rss_news(["Nico Collins"], force_refresh=False)  # served from cache
        assert len(a) == 1 and len(b) == 1
        assert spy.await_count == 1, f"cache miss: fetched {spy.await_count}x"
        print("    PASS — second call served from cache (no re-fetch)")
    asyncio.run(_cache())
    print("✅ edge cases ok")


if __name__ == "__main__":
    run_helper_tests()
    run_match_tests()
    run_edgecase_tests()
    print("\n" + "=" * 50)
    print("ALL RSS TESTS PASSED ✅")
    print("=" * 50)
