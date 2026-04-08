"""
Gemini call rate limiter and priority queue.

Enforces: max 10 Gemini calls per 30-minute rolling window.
Priority: starred players before rostered-only (though rostered-only never reach Gemini,
this queue is the single chokepoint so we keep the logic here for Phase 5 flexibility).

Usage:
    queue = get_queue()
    if queue.can_call():
        queue.record_call()
        # ... run Gemini
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

WINDOW_MINUTES = 30
MAX_CALLS_PER_WINDOW = 10


@dataclass
class QueuedItem:
    news_id: int
    player_id: str
    player_name: str
    is_starred: bool
    priority: int = field(init=False)

    def __post_init__(self):
        # Lower number = higher priority. Starred = 0, rostered-only = 1.
        self.priority = 0 if self.is_starred else 1


class NewsAnalysisQueue:
    """
    In-memory queue with rolling window rate limiter.
    Thread safety is not required — FastAPI runs in a single async event loop.
    """

    def __init__(self):
        # Timestamps of recent Gemini calls within the rolling window
        self._call_timestamps: deque[datetime] = deque()
        # Pending items: list of QueuedItem, sorted by priority
        self._pending: list[QueuedItem] = []
        # Set of news_ids already in the queue or processed (prevents duplicates)
        self._seen_ids: set[int] = set()

    # ── Rate limiting ──────────────────────────────────────────────────────────

    def _prune_window(self):
        """Remove timestamps older than the rolling window."""
        cutoff = datetime.utcnow() - timedelta(minutes=WINDOW_MINUTES)
        while self._call_timestamps and self._call_timestamps[0] < cutoff:
            self._call_timestamps.popleft()

    def can_call(self) -> bool:
        """Returns True if a Gemini call is allowed right now."""
        self._prune_window()
        return len(self._call_timestamps) < MAX_CALLS_PER_WINDOW

    def record_call(self):
        """Record that a Gemini call was just made."""
        self._call_timestamps.append(datetime.utcnow())
        logger.debug(
            f"[NewsQueue] Gemini call recorded. "
            f"{len(self._call_timestamps)}/{MAX_CALLS_PER_WINDOW} in window."
        )

    def calls_remaining(self) -> int:
        self._prune_window()
        return max(0, MAX_CALLS_PER_WINDOW - len(self._call_timestamps))

    def window_resets_at(self) -> Optional[datetime]:
        """When the oldest call in the window expires (i.e., when a slot frees up)."""
        self._prune_window()
        if not self._call_timestamps:
            return None
        return self._call_timestamps[0] + timedelta(minutes=WINDOW_MINUTES)

    # ── Queue management ───────────────────────────────────────────────────────

    def enqueue(self, item: QueuedItem) -> bool:
        """
        Add an item to the pending queue.
        Returns False if the news_id was already seen (duplicate prevention).
        """
        if item.news_id in self._seen_ids:
            return False
        self._seen_ids.add(item.news_id)
        self._pending.append(item)
        # Keep starred items first; within same priority, preserve insertion order
        self._pending.sort(key=lambda x: x.priority)
        logger.debug(
            f"[NewsQueue] enqueued news_id={item.news_id} "
            f"player={item.player_name} starred={item.is_starred} "
            f"(queue depth={len(self._pending)})"
        )
        return True

    def dequeue(self) -> Optional[QueuedItem]:
        """
        Pop the highest-priority item if a Gemini call slot is available.
        Returns None if the queue is empty or rate limit is hit.
        """
        if not self._pending:
            return None
        if not self.can_call():
            resets = self.window_resets_at()
            logger.warning(
                f"[NewsQueue] rate limit hit ({MAX_CALLS_PER_WINDOW}/{WINDOW_MINUTES}min). "
                f"Next slot at {resets}."
            )
            return None
        return self._pending.pop(0)

    def peek_next(self) -> Optional[QueuedItem]:
        """Return next item without removing it."""
        return self._pending[0] if self._pending else None

    def pending_count(self) -> int:
        return len(self._pending)

    def is_seen(self, news_id: int) -> bool:
        return news_id in self._seen_ids

    def status(self) -> dict:
        self._prune_window()
        return {
            "calls_in_window": len(self._call_timestamps),
            "calls_remaining": self.calls_remaining(),
            "pending_items": self.pending_count(),
            "window_resets_at": self.window_resets_at().isoformat() if self.window_resets_at() else None,
        }


# ── Module-level singleton ─────────────────────────────────────────────────────
# One queue per process — shared across all requests in the FastAPI event loop.
_queue: Optional[NewsAnalysisQueue] = None


def get_queue() -> NewsAnalysisQueue:
    global _queue
    if _queue is None:
        _queue = NewsAnalysisQueue()
    return _queue
