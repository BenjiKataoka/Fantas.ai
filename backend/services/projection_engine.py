"""
Standalone weighted projection engine.

compute_weighted_projection: pure function, no DB calls.
Takes raw values from each source + a weights dict.
Returns weighted result, normalized source weights, and confidence flag.

Used by both sync_projections (bulk DB sync) and the /api/projections endpoint
(on-demand, per-user weights).
"""
from config import DEFAULT_WEIGHTS
from services.utils import extract_sleeper_pts, normalize_name


def compute_weighted_projection(
    sleeper: float | None,
    espn: float | None,
    fp: float | None,
    weights: dict[str, float] | None = None,
) -> dict:
    """
    Computes a weighted average across available projection sources.

    weights: {"sleeper": float, "espn": float, "fp": float}, must sum to 1.0.
    If None, DEFAULT_WEIGHTS from config is used.

    If a source value is None, its weight is redistributed proportionally
    to the remaining sources.

    Returns:
        {
            "weighted_proj": float | None,
            "sources_used": dict | None,   # normalized weights actually applied
            "confidence_flag": str | None, # "HIGH" | "MEDIUM" | "LOW"
        }
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    w_sleeper = weights.get("sleeper", DEFAULT_WEIGHTS["sleeper"])
    w_espn = weights.get("espn", DEFAULT_WEIGHTS["espn"])
    w_fp = weights.get("fp", DEFAULT_WEIGHTS["fp"])

    available: dict[str, tuple[float, float]] = {}  # name → (value, raw_weight)
    if sleeper is not None:
        available["sleeper"] = (sleeper, w_sleeper)
    if espn is not None:
        available["espn"] = (espn, w_espn)
    if fp is not None:
        available["fp"] = (fp, w_fp)

    if not available:
        return {"weighted_proj": None, "sources_used": None, "confidence_flag": None}

    # Redistribute weight proportionally among available sources.
    total_weight = sum(w for _, w in available.values())
    if total_weight <= 0:
        # The user's weights give 0 to every source we actually have (e.g. 100% ESPN
        # for a player with no ESPN projection). Fall back to an equal split rather
        # than dividing by zero.
        n = len(available)
        normalized = {k: round(1 / n, 4) for k in available}
    else:
        normalized = {k: round(v / total_weight, 4) for k, (_, v) in available.items()}

    weighted_proj = sum(val * normalized[k] for k, (val, _) in available.items())
    weighted_proj = round(weighted_proj, 2)

    confidence_flag = {3: "HIGH", 2: "MEDIUM", 1: "LOW"}.get(len(available), "LOW")

    return {
        "weighted_proj": weighted_proj,
        "sources_used": normalized,
        "confidence_flag": confidence_flag,
    }


def weights_from_user(user) -> dict[str, float]:
    """
    Extracts projection weights from a User ORM object.
    Falls back to DEFAULT_WEIGHTS if any weight is missing.
    """
    try:
        return {
            "sleeper": float(user.weight_sleeper),
            "espn": float(user.weight_espn),
            "fp": float(user.weight_fp),
        }
    except (AttributeError, TypeError):
        return DEFAULT_WEIGHTS


def this_week_projection(sp: dict, sleeper_stats: dict | None, espn_by_id: dict, espn_by_name: dict,
                         weights: dict) -> dict:
    """One player's projection for this week from Sleeper + ESPN with the user's weights.
    Used where every player must be scored the same way (waivers, both sides of a
    matchup): FantasyPros only covers the top 10 per position, so it's left out."""
    name = sp.get("full_name") or f"{sp.get('first_name', '')} {sp.get('last_name', '')}".strip()
    espn = espn_by_id.get(str(sp.get("espn_id"))) or espn_by_name.get(normalize_name(name))
    return compute_weighted_projection(extract_sleeper_pts(sleeper_stats), espn, None, weights)
