"""Resilience primitives shared by every AI provider.

Bounded retries with exponential backoff and jitter, a circuit breaker with a
per-provider cooldown, and a concurrency limiter. Nothing here knows about a
specific provider, so the same policy applies to Groq, Gemini and OpenAI.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger(__name__)


# ── Error classification ────────────────────────────────────────────────

#: Errors that will never succeed on retry: the credential or the request is
#: wrong. Retrying these wastes quota and hides the real problem.
PERMANENT_STATUS = {400, 401, 403, 404, 422}

#: Statuses worth retrying on the SAME provider before giving up on it.
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def is_permanent_status(status: int | None) -> bool:
    """True when retrying cannot help (bad key, bad request, unknown model)."""
    return status is not None and status in PERMANENT_STATUS


def is_retryable_status(status: int | None) -> bool:
    return status is not None and status in RETRYABLE_STATUS


# ── Circuit breaker ──────────────────────────────────────────────────────

@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float | None = None


class CircuitBreaker:
    """Per-key circuit breaker with a cooldown.

    A key is "open" after ``failure_threshold`` consecutive failures and stays
    open for ``cooldown_seconds``, after which a single trial request is let
    through. A success resets the failure count immediately.
    """

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 60.0) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        self._states: dict[str, CircuitState] = {}
        self._lock = threading.Lock()

    def is_open(self, key: str) -> bool:
        with self._lock:
            state = self._states.get(key)
            if state is None or state.opened_at is None:
                return False
            if time.monotonic() - state.opened_at >= self.cooldown_seconds:
                # Cooldown elapsed: allow one trial request through.
                state.opened_at = None
                state.failures = 0
                return False
            return True

    def record_success(self, key: str) -> None:
        with self._lock:
            self._states[key] = CircuitState()

    def record_failure(self, key: str) -> None:
        with self._lock:
            state = self._states.setdefault(key, CircuitState())
            state.failures += 1
            if state.failures >= self.failure_threshold:
                state.opened_at = time.monotonic()
                logger.warning(
                    "ai_circuit_opened key=%s failures=%s cooldown_s=%.1f",
                    key, state.failures, self.cooldown_seconds,
                )

    def remaining_cooldown(self, key: str) -> float:
        with self._lock:
            state = self._states.get(key)
            if state is None or state.opened_at is None:
                return 0.0
            return max(0.0, self.cooldown_seconds - (time.monotonic() - state.opened_at))


# ── Concurrency limiting ────────────────────────────────────────────────

class ConcurrencyLimiter:
    """Caps simultaneous outbound provider calls."""

    def __init__(self, limit: int = 4) -> None:
        self._semaphore = threading.Semaphore(max(1, limit))

    @contextmanager
    def slot(self) -> Iterator[None]:
        acquired = self._semaphore.acquire(timeout=5.0)
        try:
            yield
        finally:
            if acquired:
                self._semaphore.release()


# ── Retry with backoff and jitter ───────────────────────────────────────

def backoff_delay(attempt: int, base: float, maximum: float) -> float:
    """Exponential backoff with full jitter, capped at ``maximum`` seconds."""
    ceiling = min(maximum, base * (2 ** max(0, attempt - 1)))
    return random.uniform(0, ceiling) if ceiling > 0 else 0.0


@dataclass
class RetryPolicy:
    """Bounded retry policy for a single provider attempt."""

    max_attempts: int = 2
    base_seconds: float = 0.5
    max_seconds: float = 8.0

    def delays(self) -> list[float]:
        """The sleep before each retry (one fewer than the attempt count)."""
        return [
            backoff_delay(attempt, self.base_seconds, self.max_seconds)
            for attempt in range(1, max(1, self.max_attempts))
        ]


@dataclass
class ProviderHealth:
    """Rolling per-provider counters, surfaced by the status endpoint.

    Deliberately aggregate: no request text, no user identity, no credential.
    """

    requests: int = 0
    successes: int = 0
    failures: int = 0
    rate_limited: int = 0
    timeouts: int = 0
    fallbacks: int = 0
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    last_error: str | None = None
    last_success_at: float | None = None
    cooldown_remaining_s: float = 0.0

    def record(self, *, success: bool, latency_ms: float, tokens: int = 0,
               cost_usd: float = 0.0, error: str | None = None) -> None:
        self.requests += 1
        self.total_latency_ms += latency_ms
        self.total_tokens += tokens
        self.estimated_cost_usd += cost_usd
        if success:
            self.successes += 1
            self.last_success_at = time.time()
            self.last_error = None
        else:
            self.failures += 1
            self.last_error = error

    @property
    def average_latency_ms(self) -> float:
        return round(self.total_latency_ms / self.requests, 1) if self.requests else 0.0

    def to_dict(self) -> dict:
        return {
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "rate_limited": self.rate_limited,
            "timeouts": self.timeouts,
            "fallbacks": self.fallbacks,
            "average_latency_ms": self.average_latency_ms,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "last_error": self.last_error,
            "cooldown_remaining_s": round(self.cooldown_remaining_s, 1),
        }


@dataclass
class ProviderMetrics:
    """Aggregate metrics for every provider, safe to expose over HTTP."""

    providers: dict[str, ProviderHealth] = field(default_factory=dict)

    def health(self, name: str) -> ProviderHealth:
        return self.providers.setdefault(name, ProviderHealth())

    def to_dict(self) -> dict:
        return {name: health.to_dict() for name, health in sorted(self.providers.items())}
