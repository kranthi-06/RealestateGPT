"""RealEstateGPT - Sliding-window rate limiter for general endpoints.

Process-local by design: sufficient for the current single-instance FastAPI
deployment and documented in docs/SECURITY.md. Swap for a shared store only
when horizontally scaled (then Redis/DB-backed limiting is a demonstrated
requirement, not an assumption).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, status


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int, *, enabled: bool = True) -> None:
        if not enabled:
            return
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again shortly.",
                    headers={"Retry-After": str(window_seconds)},
                )
            events.append(now)


# Reusable instances
general_limiter = RateLimiter()
auth_limiter = RateLimiter()