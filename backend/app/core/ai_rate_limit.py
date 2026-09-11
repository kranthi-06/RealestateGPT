"""Process-local protection for costly AI requests."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from app.ai.gateway import AIRateLimitError
from app.core.config import settings


class AIRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
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
            events.append(now)


ai_rate_limiter = AIRateLimiter()
