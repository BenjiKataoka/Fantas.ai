"""
Daily LLM spend guard, a hard ceiling on Gemini calls per UTC day to protect the
free-tier key. In-memory counter keyed by date; resets automatically at UTC midnight
(and on process restart, which is acceptable for a soft budget).

Tracks two things:
  1. A global daily call cap (LLM_DAILY_CALL_CAP) across all models.
  2. Per-model daily request ceilings (GEMINI_RPD_LIMITS), the free tier meters each
     model separately, and full Flash has a tiny ~20/day limit while Flash-Lite has ~500.

Shared by news_analysis_service and sentiment_service via can_spend()/record_call().
Both accept an optional `model` so callers can enforce the per-model RPD ceiling; when
omitted, only the global cap applies (backward compatible).
For a persistent, restart-proof budget this would move to a DB counter later.
"""
import logging
from datetime import datetime, timezone

from config import LLM_DAILY_CALL_CAP, GEMINI_RPD_LIMITS

logger = logging.getLogger(__name__)

_state: dict = {"date": None, "count": 0, "by_model": {}}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _roll_if_new_day() -> None:
    today = _today()
    if _state["date"] != today:
        _state["date"] = today
        _state["count"] = 0
        _state["by_model"] = {}


def can_spend(model: str | None = None) -> bool:
    """
    True if a Gemini call is allowed right now.

    Checks the global daily cap, and, when `model` is given, that model's own RPD
    ceiling. A model with headroom is never blocked by another model's exhaustion.
    """
    _roll_if_new_day()
    if _state["count"] >= LLM_DAILY_CALL_CAP:
        return False
    if model is not None:
        limit = GEMINI_RPD_LIMITS.get(model)
        if limit is not None and _state["by_model"].get(model, 0) >= limit:
            return False
    return True


def record_call(model: str | None = None) -> None:
    """Count a Gemini call against today's global budget and (if given) the model's RPD."""
    _roll_if_new_day()
    _state["count"] += 1
    if model is not None:
        _state["by_model"][model] = _state["by_model"].get(model, 0) + 1
        limit = GEMINI_RPD_LIMITS.get(model)
        if limit is not None and _state["by_model"][model] == limit:
            logger.warning(
                f"[LLMBudget] Per-model daily limit reached for {model} "
                f"({limit}), calls to this model suppressed until UTC midnight."
            )
    if _state["count"] == LLM_DAILY_CALL_CAP:
        logger.warning(
            f"[LLMBudget] Global daily cap reached ({LLM_DAILY_CALL_CAP}), "
            "further Gemini calls suppressed until UTC midnight."
        )


def usage() -> dict:
    """Current budget snapshot (for an admin/status view)."""
    _roll_if_new_day()
    return {
        "date": _state["date"],
        "calls_used": _state["count"],
        "daily_cap": LLM_DAILY_CALL_CAP,
        "remaining": max(0, LLM_DAILY_CALL_CAP - _state["count"]),
        "by_model": {
            model: {
                "used": _state["by_model"].get(model, 0),
                "limit": limit,
                "remaining": max(0, limit - _state["by_model"].get(model, 0)),
            }
            for model, limit in GEMINI_RPD_LIMITS.items()
        },
    }
