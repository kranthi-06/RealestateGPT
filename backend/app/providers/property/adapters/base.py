"""Shared adapter plumbing: request timeouts, bounded retries, provider rate
limiting, and structured logging.

Concrete adapters subclass ``BasePropertyAdapter`` and implement the four
provider operations. They must raise the typed errors from
``app.providers.property.errors`` — never silently fall back to demo data.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.providers.property.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)


class BasePropertyAdapter:
    """Rate-limited, retrying, runnable-in-thread property adapter."""

    name: str = "base"
    source_type: str = "licensed_feed"  # overridden in concrete adapters

    def __init__(
        self,
        *,
        timeout_seconds: Optional[float] = None,
        retries: Optional[int] = None,
        min_interval_seconds: Optional[float] = None,
    ) -> None:
        self._timeout = timeout_seconds if timeout_seconds is not None else settings.PROVIDER_TIMEOUT_SECONDS
        self._retries = retries if retries is not None else settings.PROVIDER_RETRIES
        self._min_interval = min_interval_seconds if min_interval_seconds is not None else settings.PROVIDER_MIN_INTERVAL_SECONDS
        self._last_call_at = 0.0

    # ── Rate limiting (adapter-level; enforced before every request) ─────
    async def _throttle(self) -> None:
        """Wait until the configured minimum interval since the last request."""
        while True:
            elapsed = time.monotonic() - self._last_call_at
            if elapsed >= self._min_interval:
                self._last_call_at = time.monotonic()
                return
            await asyncio.sleep(self._min_interval - elapsed)

    async def _guard(self, coro):
        """Apply rate limiting, retries with backoff, and typed error mapping."""
        await self._throttle()
        attempts = 0
        while True:
            attempts += 1
            try:
                return await asyncio.wait_for(coro, timeout=self._timeout)
            except asyncio.TimeoutError as exc:
                if attempts <= self._retries:
                    logger.warning("provider_timeout name=%s attempt=%s", self.name, attempts)
                    await asyncio.sleep(settings.PROVIDER_RETRY_BACKOFF_SECONDS * attempts)
                    continue
                raise ProviderTimeoutError(f"{self.name} timed out") from exc
            except Exception as exc:
                if isinstance(exc, (ProviderRateLimitError,)):
                    raise
                # Never retry provider-side validation problems twice.
                if attempts <= self._retries and _is_transient(exc):
                    logger.warning("provider_transient name=%s attempt=%s error=%s", self.name, attempts, exc)
                    await asyncio.sleep(settings.PROVIDER_RETRY_BACKOFF_SECONDS * attempts)
                    continue
                raise ProviderUnavailableError(f"{self.name} request failed: {exc}") from exc

    # ── Contract (subclasses implement, always returning normalized records) ──
    async def search(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise ProviderNotConfiguredError(f"{self.name} does not implement search")

    async def get_property(self, source_listing_id: str) -> Dict[str, Any]:
        raise ProviderNotConfiguredError(f"{self.name} does not implement get_property")

    async def refresh(self, source_listing_id: str) -> Dict[str, Any]:
        raise ProviderNotConfiguredError(f"{self.name} does not implement refresh")

    async def fetch_properties(self, cursor: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        raise ProviderNotConfiguredError(f"{self.name} does not implement fetch_properties")


def _is_transient(exc: Exception) -> bool:
    """Network-ish errors are retriable; programming errors are not."""
    import socket

    if isinstance(exc, (ConnectionError, socket.timeout, TimeoutError)):
        return True
    message = str(exc).lower()
    return any(marker in message for marker in ("timeout", "connection", "resolve", "refused", "reset"))