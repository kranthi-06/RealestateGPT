"""Process-local protection for costly AI requests.

The limiter records only requests that actually reached the provider. A request
that fails before an outbound call (a validation error, an unknown tool, a
missing conversation) must not consume the user's quota, so callers report the
outcome back through ``record`` / ``release``.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from app.ai.gateway import AIRateLimitError
from app.core.config import settings


class AIRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._pending: dict[str, float] = {}
        self._lock = Lock()

    def check(self, key: str) -> None:
        """Reserve one slot for ``key`` without yet consuming its quota."""
        if not settings.RATE_LIMIT_ENABLED:
            return
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            cutoff = now - settings.AI_RATE_LIMIT_WINDOW_SECONDS
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= settings.AI_RATE_LIMIT_REQUESTS:
                raise AIRateLimitError("Too many AI requests. Please wait a moment and try again.")
            # Reserve a slot so concurrent requests cannot race past the limit,
            # but only count it once the provider call is actually attempted.
            events.append(now)
            self._pending[key] = now

    def release(self, key: str, *, consumed: bool) -> None:
        """Drop the reservation unless the request really used the provider."""
        if not settings.RATE_LIMIT_ENABLED:
            return
        with self._lock:
            reserved = self._pending.pop(key, None)
            if consumed or reserved is None:
                return
            events = self._events.get(key)
            if events is None:
                return
            try:
                events.remove(reserved)
            except ValueError:
                pass

    def retry_after_seconds(self, key: str) -> int:
        with self._lock:
            events = self._events.get(key)
            if not events:
                return settings.AI_RATE_LIMIT_WINDOW_SECONDS
            oldest = events[0]
        remaining = settings.AI_RATE_LIMIT_WINDOW_SECONDS - (time.monotonic() - oldest)
        return max(1, int(remaining) + 1)


ai_rate_limiter = AIRateLimiter()
