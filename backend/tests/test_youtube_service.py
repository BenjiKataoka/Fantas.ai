"""Tests for youtube_service title classification and player matching.

Usage: python3 tests/test_youtube_service.py

The fixture is 400 real uploads from the @NFL channel (2026-09-15 to 09-23, covering all
of Week 2). Classification is pure string work, so the fixture is the whole test: no
network, no key, no DB.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.utils import normalize_name
from services.youtube_service import classify_title, match_players

FIXTURE = Path(__file__).parent / "fixtures" / "nfl_uploads.json"


def run_classifier_tests():
    print("\n" + "=" * 50)
    print("YOUTUBE, TITLE CLASSIFICATION")
    print("=" * 50)

    # Structured formats the NFL uses consistently.
    c = classify_title("Jared Goff's best throws from 4-TD game vs. Bills | Week 2")
    assert c == {"kind": "reel", "week": 2, "player": "Jared Goff", "opponent": "Bills"}, c
    c = classify_title("Davante Adams' best catches from 195-yard, 2-TD game | Week 2")
    assert c["kind"] == "reel" and c["player"] == "Davante Adams", c
    c = classify_title("Kenneth Walker III's best plays from 178-yard game | Week 2")
    assert c["player"] == "Kenneth Walker III", c
    print("    PASS, player reels parse the name and the opponent")

    c = classify_title("Cincinnati Bengals vs Houston Texans Game Highlights | 2026 NFL Season Week 2")
    assert c["kind"] == "game" and c["teams"] == ["Cincinnati Bengals", "Houston Texans"], c
    assert classify_title("Seattle Seahawks vs. Arizona Cardinals Game Highlights | NFL 2026")["kind"] == "game"
    print("    PASS, game highlights parse both teams, with or without the period in 'vs.'")

    assert classify_title("Every Touchdown of Week 2 | 2026 NFL Season")["kind"] == "compilation"
    assert classify_title("Top 15 Plays of Week 2! | 2026 NFL Season")["kind"] == "compilation"
    print("    PASS, weekly compilations")

    for t in ("Full Week 3 Power Rankings Show! | 2026 Season",
              "Falcons vs. Packers Week 3 Preview | NFL Daily",
              "Watch Ashton Jeanty compete on Race to the Endzone!",
              "Madison Beer was hype for the Justin Herbert TD throw",
              "Keep Josh Allen mic'd up all season",
              "GAME OF THE WEEK! Indianapolis Colts vs. Kansas City Chiefs FULL GAME"):
        assert classify_title(t)["kind"] == "noise", t
    print("    PASS, shows, previews, promos and reaction clips are noise")

    # A highlight whose verb collides with a team-result phrasing. An earlier pattern
    # matched "TAKES IT" here and threw away a real touchdown.
    assert classify_title("BROCK PURDY DROPS A DIME DOWNFIELD THEN TAKES IT IN HIMSELF")["kind"] == "play"
    print("    PASS, 'TAKES IT IN HIMSELF' stays a play, not a team result")


def run_matching_tests():
    print("\n" + "=" * 50)
    print("YOUTUBE, PLAYER MATCHING")
    print("=" * 50)
    roster = {normalize_name(n): pid for n, pid in {
        "Terrance Ferguson": "p1", "Antonio Williams": "p2",
        "Christian McCaffrey": "p3", "Amon-Ra St. Brown": "p4",
    }.items()}

    assert match_players("Matthew Stafford Connects with Terrance Ferguson for a TD", roster) == ["p1"]
    print("    PASS, full name in a play clip matches")

    # The league has many Williamses. This clip is Kyren Williams of the Rams; matching
    # on the surname put Antonio Williams of Washington on screen instead.
    assert match_players("Stafford throws a bullet to Williams for 10-yard TD", roster) == []
    print("    PASS, a bare surname matches nobody")

    assert match_players("CHRISTIAN MCCAFFREY GETS IN ANOTHER ONE", roster) == ["p3"]
    print("    PASS, ALL CAPS titles still match")
    assert match_players("Amon-Ra St. Brown's best catches from 142-yard, 2-TD game", roster) == ["p4"]
    print("    PASS, punctuation in a name survives normalization")
    assert match_players("Every Touchdown of Week 2", roster) == []
    print("    PASS, a title naming nobody matches nobody")


def run_fixture_tests():
    print("\n" + "=" * 50)
    print("YOUTUBE, 400 REAL UPLOADS")
    print("=" * 50)
    uploads = json.loads(FIXTURE.read_text())
    assert len(uploads) == 400, len(uploads)
    kinds = {}
    for u in uploads:
        kinds.setdefault(classify_title(u["title"])["kind"], []).append(u["title"])
    for k in ("game", "reel", "compilation", "play", "noise"):
        print(f"    {k:<12} {len(kinds.get(k, [])):>4}")

    # Week 2 had 16 games and every one was posted. If this drops, either the NFL
    # changed its title format or the pattern broke; both mean the page loses its spine.
    assert len(kinds["game"]) >= 16, f"only {len(kinds['game'])} game highlights"
    assert len(kinds["reel"]) >= 15, f"only {len(kinds['reel'])} player reels"
    # Noise must stay a minority: if it balloons, the pattern is eating real highlights.
    assert len(kinds["noise"]) < len(uploads) * 0.25, "noise pattern is too greedy"
    print("    PASS, all 16 Week 2 games present, reels and noise within range")

    for t in kinds["game"]:
        c = classify_title(t)
        assert len(c["teams"]) == 2 and all(c["teams"]), t
    print("    PASS, every game highlight yields two team names")


def run_window_tests():
    """A date window is what places the clips whose titles never say a week."""
    import asyncio
    from unittest.mock import patch
    from services import youtube_service as yt

    print("\n" + "=" * 50)
    print("YOUTUBE, WEEK WINDOW")
    print("=" * 50)
    uploads = json.loads(FIXTURE.read_text())
    fake = [{"video_id": u["video_id"], "title": u["title"],
             "published_at": u["published_at"], "thumbnail": ""} for u in uploads]

    async def fake_fetch(*a, **k):
        return fake

    with patch.object(yt, "get_channel_uploads", fake_fetch):
        wk2 = asyncio.run(yt.highlights_for({}, week=2, since="2026-09-18", until="2026-09-23"))
        wk1 = asyncio.run(yt.highlights_for({}, week=1, since="2026-09-09", until="2026-09-17"))

    titles2 = [g["title"] for g in wk2["games"]]
    assert len(titles2) == 16, f"Week 2 should have all 16 games, got {len(titles2)}"
    print(f"    PASS, Week 2 window returns all 16 games")

    # This one's title never says a week, so only the publish date can place it.
    browns = [t for t in titles2 if "Cleveland Browns" in t]
    assert browns, "the untagged Browns game should land in Week 2"
    print("    PASS, the untitled-week Browns game lands in Week 2 by publish date")
    assert not [g["title"] for g in wk1["games"] if "Cleveland Browns" in g["title"]], \
        "the Browns game leaked into Week 1"
    print("    PASS, and does not leak into Week 1")


if __name__ == "__main__":
    run_classifier_tests()
    run_matching_tests()
    run_fixture_tests()
    run_window_tests()
    print("\n✅ All YouTube service tests passed.")
