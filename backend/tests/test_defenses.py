"""
Team defenses: they are rostered, projected and ranked like anyone else, but never
sent through the Gemini pipeline.

Hits the live sources, like test_espn_service does, because the whole point of this
path is that three upstream feeds each key a defense differently:
  Sleeper     player_id "HOU", name "Houston Texans", espn_id None
  ESPN        id -16034, fullName "Texans D/ST"
  FantasyPros "houston texans"

Run: venv/bin/python tests/test_defenses.py
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from services import espn_service, fp_service, sleeper_service, tracker_service
from services.league_service import RELEVANT_POSITIONS
from services.projection_service import get_nfl_state
from services.utils import normalize_name


async def test_sync_filter_keeps_defenses():
    """The roster sync's position gate is what dropped DEF for both platforms."""
    assert "DEF" in RELEVANT_POSITIONS, RELEVANT_POSITIONS
    print("  sync filter keeps DEF")


async def test_def_espn_id_matches_espn():
    """We derive a defense's ESPN id from its team because Sleeper stores none.
    If ESPN ever changes that scheme, every defense silently loses its ESPN column."""
    season = (await get_nfl_state())["season"]
    # ESPN returns nothing for a slot-only filter; it needs the sort key too.
    fh = json.dumps({"players": {"limit": 100, "filterSlotIds": {"value": [16]},
                                 "sortDraftRanks": {"sortPriority": 100, "sortAsc": True,
                                                    "value": "PPR"}}})
    url = f"{espn_service.ESPN_BASE}/seasons/{season}/segments/0/leaguedefaults/3"
    async with httpx.AsyncClient(timeout=25) as c:
        resp = await c.get(url, headers={"X-Fantasy-Filter": fh, "Accept": "application/json"},
                           params={"view": "kona_player_info"})
    rows = resp.json().get("players", [])
    assert len(rows) == 32, f"expected 32 D/ST, got {len(rows)}"

    for e in rows:
        pl = e["player"]
        team = espn_service.PRO_TEAM_ID.get(pl["proTeamId"])
        assert team, f"unmapped proTeamId {pl['proTeamId']}"
        assert espn_service.DEF_ESPN_ID[team] == str(pl["id"]), f"{team}: {pl['id']}"
    print(f"  DEF_ESPN_ID matches ESPN for {len(rows)}/32 defenses")


async def test_all_three_sources_project_defenses():
    """A defense must reach the weighted engine from more than one source, or it lands
    with a LOW confidence flag every week."""
    state = await get_nfl_state()
    if state["season_type"] not in ("regular", "post"):
        print("  skipped, offseason has no weekly projections")
        return
    season, week = state["season"], state["week"]

    pool = await sleeper_service.get_all_players()
    defenses = {pid: p for pid, p in pool.items() if p.get("position") == "DEF"}
    assert len(defenses) == 32, f"expected 32 defenses in the Sleeper pool, got {len(defenses)}"

    sleeper_proj = await sleeper_service.get_projections(season, week)
    hit = [pid for pid in defenses if pid in sleeper_proj]
    assert len(hit) >= 30, f"Sleeper projected only {len(hit)}/32 defenses"
    print(f"  Sleeper: {len(hit)}/32 defenses projected")

    by_id, _ = await espn_service.get_espn_projections_full(season, week)
    espn_hit = [pid for pid in defenses if espn_service.DEF_ESPN_ID.get(pid) in by_id]
    assert len(espn_hit) >= 30, f"ESPN projected only {len(espn_hit)}/32 defenses"
    print(f"  ESPN:    {len(espn_hit)}/32 defenses projected (matched by derived id)")

    # FantasyPros serves only the top 10 rows per position to non-JS clients (known, see
    # plan.md), so the bar is that the names it does return match ours, not that all 32 do.
    fp = await fp_service.get_fp_projections(week)
    ours = {normalize_name(f"{p.get('first_name', '')} {p.get('last_name', '')}".strip())
            for p in defenses.values()}
    fp_def = [k for k in fp if k in ours]
    assert len(fp_def) >= 8, f"FantasyPros matched only {len(fp_def)} defense names"
    print(f"  FP:      {len(fp_def)} defenses matched by name (top-10 page)")


async def test_market_pool_ranks_defenses_by_team():
    """The market job looks a defense up by its player_id, since ESPN's "Texans D/ST"
    never normalizes to our "Houston Texans"."""
    state = await get_nfl_state()
    if state["season_type"] not in ("regular", "post"):
        print("  skipped, offseason")
        return
    pool = await espn_service.get_espn_market_pool(state["season"], state["week"])
    assert pool, "empty market pool"
    ranked = [t for t in espn_service.PRO_TEAM_ID.values()
              if pool.get(t) and pool[t]["position_rank"]]
    assert len(ranked) >= 30, f"only {len(ranked)}/32 defenses ranked"
    # Adding D/ST must not have cost skill players their place in the pool.
    skill = sum(1 for v in pool.values() if v["position"] in ("QB", "RB", "WR", "TE", "K"))
    assert skill >= 500, f"skill-player pool shrank to {skill}"
    print(f"  market pool: {len(ranked)}/32 defenses ranked, {skill} skill players kept")


async def test_defenses_excluded_from_the_gemini_pipeline():
    """Projections yes, 4-pass profile no: a defense has no career stats, ADP or news."""
    from database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        every = await tracker_service.get_trackable_players(db)
        profilable = await tracker_service.get_trackable_players(db, profilable_only=True)

    ids = {pid for pid, _ in every}
    kept = {pid for pid, _ in profilable}
    teams = set(espn_service.PRO_TEAM_ID.values())
    rostered_defenses = ids & teams

    assert kept <= ids, "profilable set is not a subset of the trackable set"
    assert not (kept & teams), f"defenses reached the Gemini work list: {kept & teams}"
    assert len(ids) - len(kept) == len(rostered_defenses), "dropped something other than defenses"
    print(f"  {len(rostered_defenses)} rostered defenses tracked for rank, 0 sent to Gemini "
          f"({len(kept)} players profilable)")

    # The per-user roster query the batch deep-dive and its progress poll both use.
    async with AsyncSessionLocal() as db:
        analyzable = await tracker_service._analyzable_roster(db, 1)
    assert not (set(analyzable) & teams), "a defense reached the roster deep-dive"
    print(f"  user 1 roster deep-dive: {len(analyzable)} players, no defenses")




async def test_defenses_reach_the_waiver_board():
    """Streaming a defense is a normal waiver move, so free-agent defenses have to be
    rankable: a position in POSITIONS, a projection, and a % rostered the board can show."""
    from services import waiver_service

    assert "DEF" in waiver_service.POSITIONS, waiver_service.POSITIONS

    state = await get_nfl_state()
    if state["season_type"] not in ("regular", "post"):
        print("  skipped, offseason")
        return

    # The market lookup is the part that breaks silently: a defense is keyed by team
    # abbreviation, not by a normalized name.
    pool = await espn_service.get_espn_market_pool(state["season"], state["week"])
    sample = [t for t in espn_service.PRO_TEAM_ID.values()
              if (pool.get(t) or {}).get("percent_rostered") is not None]
    assert len(sample) >= 30, f"only {len(sample)}/32 defenses carry a % rostered"
    print(f"  {len(sample)}/32 defenses have a % rostered under their team key")


async def main():
    tests = [
        test_sync_filter_keeps_defenses,
        test_def_espn_id_matches_espn,
        test_all_three_sources_project_defenses,
        test_market_pool_ranks_defenses_by_team,
        test_defenses_reach_the_waiver_board,
        test_defenses_excluded_from_the_gemini_pipeline,
    ]
    failed = 0
    for t in tests:
        print(f"\n{t.__name__}")
        try:
            await t()
        except Exception as e:
            failed += 1
            print(f"  FAIL: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
