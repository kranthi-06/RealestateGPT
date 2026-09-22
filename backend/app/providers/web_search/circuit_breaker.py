"""Provider circuit breaker: healthy -> degraded -> open -> half-open.

When a provider repeatedly fails we temporarily stop hammering it, then after
``cooldown_seconds`` allow a single half-open test request. Success returns the
breaker to ``healthy``; failure reopens it.
"""
from __future__ import annotations

import threading
import time

from app.providers.web_search.models import WebSearchError

# Failure thresholds per window.
_FAILURE_THRESHOLD = 3
_WINDOW_SECONDS = 120.0
_COOLDOWN_SECONDS = 60.0
_MAX_ERROR_CAUSES = 3


class CircuitBreaker:
    """Thread-safe provider circuit breaker."""

    def __init__(
        self,
        failure_threshold: int = _FAILURE_THRESHOLD,
        window_seconds: float = _WINDOW_SECONDS,
        cooldown_seconds: float = _COOLDOWN_SECONDS,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._state = "healthy"  # healthy | degraded | open | half_open
        self._failures: list[float] = []
        self._opened_at: float | None = None
        self._last_error: str | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open" and self._opened_at is not None:
                if time.monotonic() - self._opened_at >= self.cooldown_seconds:
                    self._state = "half_open"
            return self._state

    def allow_request(self) -> bool:
        """True when a provider request is permitted right now."""
        with self._lock:
            if self._state == "open":
                if self._opened_at is not None and time.monotonic() - self._opened_at >= self.cooldown_seconds:
                    self._state = "half_open"
                    return True
                return False
            if self._state == "half_open":
                return True  # single test request; the caller reports success/failure
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()
            self._opened_at = None
            self._last_error = None
            self._state = "healthy"

    def record_failure(self, exc: BaseException) -> None:
        with self._lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds
            self._failures = [ts for ts in self._failures if ts > cutoff]
            self._failures.append(now)
            self._last_error = str(getattr(exc, "message", None) or exc)[:500]
            if self._state == "half_open":
                self._state = "open"
                self._opened_at = now
            elif len(self._failures) >= self.failure_threshold:
                self._state = "open"
                self._opened_at = now
            elif self._failures:
                self._state = "degraded"

    def snapshot(self) -> dict:
        state = self.state
        return {
            "state": state,
            "failures_in_window": len(self._failures),
            "cooldown_seconds": self.cooldown_seconds,
            "last_failure_reason": self._last_error,
        }

    def should_block(self, exc: BaseException) -> bool:
        """Whether a WebSearchError should NOT be retried because the breaker opened.

        Non-retryable errors (auth/invalid request) bypass the breaker silently.
        """
        if isinstance(exc, WebSearchError):
            return exc.retryable
        return True