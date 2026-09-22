"""
Portfolio: every player a user owns across all their leagues, listed once, with exposure.

Pure functions, no I/O. The router syncs the leagues and loads the rows, then calls
build_portfolio().
"""


def build_portfolio(rows: list[dict], projections: dict[str, dict], stock: dict[str, dict],
                    league_count: int) -> dict:
    """rows: one per (league, player) from my_roster, with player and league fields.
    Returns {"players": [...], "summary": {...}}; each player carries the leagues he's on
    and whether he's in that league's starting lineup."""
    players: dict[str, dict] = {}
    for r in rows:
        p = players.get(r["player_id"])
        if not p:
            proj = projections.get(r["player_id"]) or {}
            p = players[r["player_id"]] = {
                "player_id": r["player_id"], "name": r["name"], "position": r["position"],
                "nfl_team": r["nfl_team"], "injury_status": r["injury_status"] or "Active",
                "weighted_proj": proj.get("weighted_proj"), "confidence_flag": proj.get("confidence_flag"),
                "stock": stock.get(r["player_id"]), "leagues": [],
            }
        p["leagues"].append({"league_id": r["league_id"], "platform": r["platform"], "name": r["league_name"],
                             "is_starter": r["is_starter"], "slot": r["slot"]})

    for p in players.values():
        p["held"] = len(p["leagues"])
        p["starting"] = sum(l["is_starter"] for l in p["leagues"])
        p["leagues"].sort(key=lambda l: (not l["is_starter"], l["name"] or ""))

    ranked = sorted(players.values(), key=lambda p: (-p["starting"], -p["held"], -(p["weighted_proj"] or 0)))
    biggest = max(ranked, key=lambda p: (p["held"], p["starting"], p["weighted_proj"] or 0)) if ranked else None
    return {
        "players": ranked,
        "summary": {
            "leagues": league_count,
            "players": len(ranked),
            "starting_slots": sum(p["starting"] for p in ranked),
            # Projected points you actually have in lineups this week, across every league.
            "projected_points": round(sum((p["weighted_proj"] or 0) * p["starting"] for p in ranked), 1),
            # Only worth calling out when someone is on more than one of your teams.
            "biggest_exposure": ({"player_id": biggest["player_id"], "name": biggest["name"],
                                  "held": biggest["held"]} if biggest and biggest["held"] > 1 else None),
        },
    }
