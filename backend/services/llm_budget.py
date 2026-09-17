"""
Daily LLM spend guard — a hard ceiling on Gemini calls per UTC day to protect the
free-tier key. In-memory counter keyed by date; resets automatically at UTC midnight
(and on process restart, which is acceptable for a soft budget).

Shared by news_analysis_service and sentiment_service via can_spend()/record_call().
For a persistent, restart-proof budget this would move to a DB counter later.
"""
import logging
from datetime import datetime, timezone

from config import LLM_DAILY_CALL_CAP

logger = logging.getLogger(__name__)

_state = {"date": None, "count": 0}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _roll_if_new_day() -> None:
    today = _today()
    if _state["date"] != today:
        _state["date"] = today
        _state["count"] = 0


def can_spend() -> bool:
    """True if we're under today's Gemini call cap."""
    _roll_if_new_day()
    return _state["count"] < LLM_DAILY_CALL_CAP


def record_call() -> None:
    """Count a Gemini call against today's budget. Logs when the cap is reached."""
    _roll_if_new_day()
    _state["count"] += 1
    if _state["count"] == LLM_DAILY_CALL_CAP:
        logger.warning(
            f"[LLMBudget] Daily cap reached ({LLM_DAILY_CALL_CAP}) — "
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
    }
