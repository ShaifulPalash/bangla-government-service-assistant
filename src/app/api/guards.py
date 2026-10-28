"""Two small protections for the API: an answer cache and a rate limiter.

Both live in memory (no extra libraries, nothing to install). They are reset when the
server restarts, which is fine: the cache only saves time, and the limiter only needs to
count the last minute.
"""

from __future__ import annotations

import math
import re
import time
from collections import OrderedDict, deque
from collections.abc import Callable

# Outcomes worth remembering. "unavailable" must NOT be cached: it is a temporary problem.
CACHEABLE_DECISIONS = {"answer", "clarify", "refuse"}


def cache_key(question: str) -> str:
    """Same question, same key: lowercase, spaces collapsed.

    Callers pass the question AFTER personal numbers were replaced, so a private number
    can never end up inside a cache key.
    """
    return re.sub(r"\s+", " ", question.strip().lower())


class AnswerCache:
    """Remembers recent results. Old entries expire; the oldest are dropped when full."""

    def __init__(
        self,
        max_items: int = 200,
        ttl_seconds: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._items: OrderedDict[str, tuple[float, dict]] = OrderedDict()

    def get(self, question: str) -> dict | None:
        key = cache_key(question)
        entry = self._items.get(key)
        if entry is None:
            return None
        stored_at, result = entry
        if self.clock() - stored_at > self.ttl_seconds:
            del self._items[key]  # expired
            return None
        self._items.move_to_end(key)  # recently used entries stay longest
        return result

    def put(self, question: str, result: dict) -> None:
        if result.get("decision") not in CACHEABLE_DECISIONS:
            return
        key = cache_key(question)
        self._items[key] = (self.clock(), result)
        self._items.move_to_end(key)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)  # drop the oldest

    def __len__(self) -> int:
        return len(self._items)


class RateLimiter:
    """Allows at most `limit` requests per visitor in any `window_seconds` period."""

    def __init__(
        self,
        limit: int = 10,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        max_visitors: int = 5000,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self.max_visitors = max_visitors
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, visitor: str) -> tuple[bool, int]:
        """Return (allowed, seconds to wait). Counts the request when it is allowed."""
        now = self.clock()
        hits = self._hits.setdefault(visitor, deque())
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()  # forget requests outside the window
        if len(hits) >= self.limit:
            wait = math.ceil(self.window_seconds - (now - hits[0]))
            return False, max(wait, 1)
        hits.append(now)
        self._hits.move_to_end(visitor)
        while len(self._hits) > self.max_visitors:  # keep memory bounded
            self._hits.popitem(last=False)
        return True, 0
