"""Bounded retry policy for external web search providers.

Retries
-------
Retryable: 429, 502, 503, 504, timeouts, and temporary network failures.
Never retried: 401, 403, invalid keys, malformed requests, unsupported queries.

Algorithm: bounded exponential backoff with full jitter and an optional
``Retry-After`` header override. ``max_retries`` comes from
``WEB_SEARCH_MAX_RETRIES`` (attempts beyond the first).
"""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

from app.providers.web_search.models import (
    WebSearchAuthenticationError,
    WebSearchError,
    WebSearchInvalidRequestError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
    WebSearchUnavailableError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _backoff_delay(attempt: int, base: float, max_delay: float, retry_after: float | None) -> float:
    if retry_after is not None and retry_after >= 0:
        return max(0.0, min(float(retry_after), max_delay))
    delay = base * (2 ** attempt)
    return random.uniform(0, min(delay, max_delay))


def is_retryable_error(exc: BaseException) -> bool:
    """True when the error qualifies for a bounded retry."""
    if isinstance(exc, (WebSearchRateLimitError, WebSearchTimeoutError, WebSearchUnavailableError)):
        return True
    if isinstance(exc, (WebSearchAuthenticationError, WebSearchInvalidRequestError)):
        return False
    # httpx transport errors (connect/timeout) are temporary network failures.
    try:
        import httpx

        if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
            return True
    except ImportError:  # pragma: no cover - httpx is always installed here
        pass
    return False


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_retries: int,
    timeout_seconds: float,
    base_backoff: float = 0.5,
    max_backoff: float = 8.0,
) -> T:
    """Execute ``fn`` once with bounded retries and exponential backoff + jitter.

    ``max_retries`` counts attempts after the first. ``fn`` is expected to raise
    :class:`WebSearchError` (including rate-limit/timeout/unavailable) or httpx
    transport errors. Non-retryable errors re-raise immediately.
    """
    attempts = max(0, int(max_retries))
    last_error: BaseException | None = None
    for attempt in range(attempts + 1):
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001 - central retry policy
            retry_after = None
            if isinstance(exc, WebSearchRateLimitError):
                retry_after = exc.retry_after
            last_error = exc
            if attempt >= attempts or not is_retryable_error(exc):
                raise
            delay = _backoff_delay(attempt, base_backoff, max_backoff, retry_after)
            logger.info(
                "web_search_retry attempt=%s/%s delay_ms=%s error=%s",
                attempt + 1, attempts, round(delay * 1000, 1), getattr(exc, "code", type(exc).__name__),
            )
            time.sleep(delay)
    assert last_error is not None
    raise last_error