"""In-memory TTL cache shared by every upstream service.

Six services each kept their own `_cache` dict plus a copy of these two functions.
Three copies were byte for byte identical, one stored its entries as dicts instead of
tuples, and two held a single value under a fixed key. Each service still owns its own
store, so a Sleeper key can never collide with an ESPN one; only the mechanics are shared.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TTLCache:
    """One service's cache. Entries expire on read, which is enough here: the stores hold
    tens of keys, so nothing needs sweeping."""

    def __init__(self, default_ttl_hours: float = 6.0):
        self._entries: dict[str, tuple[Any, datetime]] = {}
        self.default_ttl_hours = default_ttl_hours

    def get(self, key: str) -> Optional[Any]:
        """The cached value, or None when it is missing or expired."""
        entry = self._entries.get(key)
        if entry and datetime.utcnow() < entry[1]:
            return entry[0]
        return None

    def set(self, key: str, data: Any, ttl_hours: Optional[float] = None) -> Any:
        """Store a value and return it, so callers can `return cache.set(key, data)`."""
        ttl = self.default_ttl_hours if ttl_hours is None else ttl_hours
        self._entries[key] = (data, datetime.utcnow() + timedelta(hours=ttl))
        return data

    def set_minutes(self, key: str, data: Any, ttl_minutes: float) -> Any:
        """Same, for the news scrapers that think in minutes."""
        return self.set(key, data, ttl_hours=ttl_minutes / 60)

    def clear(self) -> None:
        self._entries.clear()
