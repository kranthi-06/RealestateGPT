"""Web search provider registry and status store.

``get_web_search_provider()`` returns the provider selected by
``WEB_SEARCH_PROVIDER``. A missing configuration yields the typed
``WEB_SEARCH_NOT_CONFIGURED`` state through the provider's own error contract —
the application NEVER substitutes fake or demo results.
"""
from __future__ import annotations

import logging
import time
import threading
from typing import Dict, Optional

from app.core.config import settings
from app.providers.web_search.base import BaseWebSearchProvider
from app.providers.web_search.models import (
    WebSearchProviderStatus,
    WebSearchNotConfiguredError,
)

logger = logging.getLogger(__name__)

REGISTRY: Dict[str, type[BaseWebSearchProvider]] = {}


def register(name: str, provider_cls: type[BaseWebSearchProvider]) -> None:
    REGISTRY[name] = provider_cls


def registered_providers() -> list[str]:
    return sorted(REGISTRY)


def get_web_search_provider() -> BaseWebSearchProvider:
    """Return the configured provider adapter (module-level override supported)."""
    name = (settings.WEB_SEARCH_PROVIDER or "").strip().lower()
    if name == "brave":
        from app.providers.web_search.brave import BraveSearchProvider
        return BraveSearchProvider()
    if name == "searxng":
        from app.providers.web_search.searxng import SearXNGSearchProvider
        return SearXNGSearchProvider()
    if not name:
        raise WebSearchNotConfiguredError("WEB_SEARCH_PROVIDER is not configured.")
    raise WebSearchNotConfiguredError(
        f"Web search provider '{name}' is not registered. Registered: {', '.join(registered_providers()) or 'none'}."
    )


class WebSearchProviderHealth:
    """Process-local metric aggregation for the configured provider."""

    def __init__(self) -> None:
        self._requests = 0
        self._success = 0
        self._too_many_requests = 0
        self._errors = 0
        self._latency: list[float] = []
        self._cache_hits = 0
        self._cache_misses = 0
        self._last_failure_reason: Optional[str] = None
        self._last_checked_at: Optional[float] = None
        self._lock = threading.Lock()

    def record_start(self) -> None:
        with self._lock:
            self._requests += 1
            self._last_checked_at = time.monotonic()

    def record_success(self, latency_ms: float) -> None:
        with self._lock:
            self._success += 1
            self._latency = (self._latency + [latency_ms])[-100:]

    def record_rate_limited(self) -> None:
        with self._lock:
            self._too_many_requests += 1
            self._errors += 1

    def record_error(self, reason: str) -> None:
        with self._lock:
            self._errors += 1
            self._last_failure_reason = (reason or "")[:300]

    def record_cache(self, hit: bool) -> None:
        with self._lock:
            if hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

    def snapshot(self) -> WebSearchProviderStatus:
        with self._lock:
            used = self._requests - self._success
            state = "healthy"
            if not settings.web_search_configured:
                state = "not_configured"
            elif self._errors and used >= 3:
                state = "degraded"
            return WebSearchProviderStatus(
                status=state,
                provider=settings.WEB_SEARCH_PROVIDER,
                requests=self._requests,
                success=self._success,
                too_many_requests=self._too_many_requests,
                errors=self._errors,
                average_latency_ms=round(sum(self._latency) / len(self._latency), 1) if self._latency else 0.0,
                cache_hit_rate=round(self._cache_hits / (self._cache_hits + self._cache_misses), 3)
                if (self._cache_hits + self._cache_misses) else 0.0,
                last_failure_reason=self._last_failure_reason,
            )


_health_store: Optional[WebSearchProviderHealth] = None
_health_lock = threading.Lock()


def web_search_health() -> WebSearchProviderHealth:
    global _health_store
    if _health_store is None:
        with _health_lock:
            if _health_store is None:
                _health_store = WebSearchProviderHealth()
    return _health_store


# Idempotent registration of the Brave adapter.
from app.providers.web_search.brave import BraveSearchProvider  # noqa: E402
from app.providers.web_search.searxng import SearXNGSearchProvider  # noqa: E402

if "brave" not in REGISTRY:
    register("brave", BraveSearchProvider)

if "searxng" not in REGISTRY:
    register("searxng", SearXNGSearchProvider)