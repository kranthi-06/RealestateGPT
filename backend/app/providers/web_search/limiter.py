"""Provider + per-user rate limiting and concurrency guard for web search.

* Global provider RPM floor (``WEB_SEARCH_RPM``, default 60/min) so one tenant
  can never consume an entire paid quota.
* Per-user window (``WEB_SEARCH_RPM_PER_USER``, default 30/min) exposed as an
  honest 429 in the API layer.
* Concurrency guard (``WEB_SEARCH_CONCURRENCY``) bounding parallel requests.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.providers.web_search.models import WebSearchRateLimitError

DEFAULT_GLOBAL_RPM = 60
DEFAULT_PER_USER_RPM = 30


class _Window:
    def __init__(self) -> None:
        self.events: deque[float] = deque()

    def allow(self, now: float, limit: int, window_seconds: float) -> float:
        """Return seconds to wait, or 0 when allowed."""
        cutoff = now - window_seconds
        while self.events and self.events[0] <= cutoff:
            self.events.popleft()
        if len(self.events) >= limit:
            wait = self.events[0] + window_seconds - now
            return max(0.0, wait)
        self.events.append(now)
        return 0.0


class WebSearchLimiter:
    def __init__(self, global_rpm: float, per_user_rpm: float, concurrency: int) -> None:
        self._global = _Window()
        self._users: dict[str, _Window] = defaultdict(_Window)
        self._active_requests = 0
        self._lock = threading.Lock()
        self._global_rpm = max(1, int(global_rpm))
        self._per_user_rpm = max(1, int(per_user_rpm))
        self._concurrency = max(1, int(concurrency))

    def acquire(self, user_key: str = "anonymous") -> None:
        """Block (with tiny sleeps) until a global + per-user slot is available.

        Raises :class:`WebSearchRateLimitError` when the user window is exhausted
        instead of silently degrading the provider.
        """
        user_key = (user_key or "anonymous")[:120]
        for _ in range(300):  # bounded wait (~30s)
            now = time.monotonic()
            with self._lock:
                if self._active_requests >= self._concurrency:
                    time.sleep(0.05)
                    continue
                user_wait = self._users[user_key].allow(now, self._per_user_rpm, 60.0)
                if user_wait > 30:
                    raise WebSearchRateLimitError(
                        "Too many web discovery requests. Please try again shortly.",
                        retry_after=user_wait,
                    )
                global_wait = self._global.allow(now, self._global_rpm, 60.0)
                if global_wait > 0:
                    time.sleep(min(global_wait, 1.0))
                    continue
                self._active_requests += 1
                if global_wait == 0 and user_wait == 0:
                    return
                self._active_requests -= 1
        raise WebSearchRateLimitError(
            "Web search provider is busy. Please try again shortly.",
            retry_after=1.0,
        )

    def release(self) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "global_rpm": self._global_rpm,
                "per_user_rpm": self._per_user_rpm,
                "concurrency": self._concurrency,
                "active_requests": self._active_requests,
            }


_default_limiter: WebSearchLimiter | None = None


def get_web_search_limiter() -> WebSearchLimiter:
    """Process-wide default limiter bound to settings (lazily constructed)."""
    global _default_limiter
    if _default_limiter is None:
        from app.core.config import settings

        global_rpm = settings.WEB_SEARCH_RPM or DEFAULT_GLOBAL_RPM
        _default_limiter = WebSearchLimiter(
            global_rpm=global_rpm,
            per_user_rpm=DEFAULT_PER_USER_RPM,
            concurrency=settings.WEB_SEARCH_CONCURRENCY,
        )
    return _default_limiter