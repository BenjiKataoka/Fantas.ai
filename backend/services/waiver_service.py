"""
Waiver wire: rank one league's free agents by how much they'd improve your lineup.

Pure functions, no I/O. The router builds projected player rows for the free agents and
your roster, then calls rank_free_agents().
"""
from services.recap_service import best_lineup

POSITIONS = ("QB", "RB", "WR", "TE", "K")
MIN_UPGRADE = 0.5  # smaller gains are projection noise, not a reason to burn a claim


def _proj(p: dict) -> float:
    return p.get("proj") or 0.0


def rank_free_agents(free_agents: list[dict], roster: list[dict], slots: list[str],
                     per_position: int = 15) -> list[dict]:
    """Each free agent gets `upgrade` (projected lineup points gained by adding him) and
    `replaces` (the starter he'd push out). Re-solving the lineup with him added handles
    FLEX and SUPER_FLEX without special cases. Keeps the top `per_position` per position."""
    base = best_lineup(roster, slots, _proj)
    base_total = sum(_proj(p) for p in base)

    ranked = []
    for fa in free_agents:
        after = best_lineup(roster + [fa], slots, _proj)
        gain = sum(_proj(p) for p in after) - base_total
        after_ids = {a["player_id"] for a in after}
        out = next((p for p in base if p["player_id"] not in after_ids), None)
        upgrade = round(gain, 2) if gain >= MIN_UPGRADE else 0.0
        ranked.append({
            **fa,
            "upgrade": upgrade,
            # No one pushed out but a gain means he fills a slot you have nobody for.
            "replaces": {"player_id": out["player_id"], "name": out["name"], "proj": out.get("proj")}
                        if upgrade and out else None,
        })

    ranked.sort(key=lambda p: (p["upgrade"], _proj(p)), reverse=True)
    kept, counts = [], {}
    for p in ranked:
        counts[p["position"]] = counts.get(p["position"], 0) + 1
        if counts[p["position"]] <= per_position:
            kept.append(p)
    return kept
