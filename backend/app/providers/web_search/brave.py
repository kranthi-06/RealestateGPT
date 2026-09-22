"""Brave Search API adapter (authorized Web Search API, not scraping).

Endpoint: ``https://api.search.brave.com/res/v1/web/search``

Requests carry the API key in the server-side ``X-Subscription-Token`` header and
default to ``country=IN`` / ``search_lang=en`` for Indian property discovery
(both configurable via settings). Only fields the provider actually returns are
mapped into the normalized :class:`WebSearchResult`; missing fields remain
``None``.

Typed failure contract
----------------------
* No API key            -> :class:`WebSearchNotConfiguredError` (never fake results)
* 401 / 403             -> :class:`WebSearchAuthenticationError` (never retried)
* 429 (with Retry-After)-> :class:`WebSearchRateLimitError`
* 500/502/503/504       -> :class:`WebSearchUnavailableError`
* timeout               -> :class:`WebSearchTimeoutError`
* malformed body        -> :class:`WebSearchInternalError`
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.providers.web_search.base import BaseWebSearchProvider
from app.providers.web_search.circuit_breaker import CircuitBreaker
from app.providers.web_search.models import (
    WebSearchAuthenticationError,
    WebSearchInternalError,
    WebSearchInvalidRequestError,
    WebSearchNotConfiguredError,
    WebSearchRateLimitError,
    WebSearchResponse,
    WebSearchResult,
    WebSearchTimeoutError,
    WebSearchUnavailableError,
)
from app.providers.web_search.retry import retry_with_backoff
from app.providers.web_search.security import validate_result_url

logger = logging.getLogger(__name__)

_BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_PROVIDER_NAME = "brave"


def _parse_domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host.removeprefix("www.")
    except ValueError:
        return ""


def _parse_page_fetched(raw: Any) -> Optional[datetime]:
    """Brave may return ``page_fetched`` as an ISO-8601-ish string; tolerate None."""
    if not raw:
        return None
    try:
        text = str(raw).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None


def _short_id(url: str, index: int) -> str:
    return f"brave-{_parse_domain(url) or 'web'}-{index}"


class BraveSearchProvider(BaseWebSearchProvider):
    """Normalized Brave Search web-result adapter."""

    name = _BRAVE_PROVIDER_NAME

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__()
        self.api_key = api_key if api_key is not None else settings.BRAVE_SEARCH_API_KEY
        self.circuit = CircuitBreaker()
        self._latency: list[float] = []

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(settings.WEB_SEARCH_TIMEOUT_SECONDS),
            headers={
                "X-Subscription-Token": self.api_key or "",
                "Accept": "application/json",
            },
        )

    def search(
        self,
        query: str,
        country: Optional[str] = None,
        language: Optional[str] = None,
        count: int = 20,
        offset: int = 0,
        freshness: Optional[str] = None,
    ) -> WebSearchResponse:
        if not self.api_key:
            raise WebSearchNotConfiguredError(
                "BRAVE_SEARCH_API_KEY is not configured. Web discovery is unavailable until it is set."
            )
        if self.circuit.state == "open":
            raise WebSearchUnavailableError(
                "Web search provider is temporarily unavailable (circuit open)."
            )
        query = (query or "").strip()
        if not query:
            raise WebSearchInvalidRequestError("A search query is required.")

        count = max(1, min(int(count), settings.WEB_SEARCH_MAX_RESULTS))
        offset = max(0, int(offset))

        started = time.perf_counter()
        try:
            response = retry_with_backoff(
                lambda: self._request(
                    query=query,
                    country=country or settings.WEB_SEARCH_COUNTRY,
                    language=language or settings.WEB_SEARCH_LANGUAGE,
                    count=count,
                    offset=offset,
                    freshness=freshness,
                ),
                max_retries=settings.WEB_SEARCH_MAX_RETRIES,
                timeout_seconds=settings.WEB_SEARCH_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            self.circuit.record_failure(exc)
            raise
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        self._latency = (self._latency + [latency_ms])[-100:]
        self.circuit.record_success()
        return response

    def _request(
        self,
        query: str,
        country: str,
        language: str,
        count: int,
        offset: int,
        freshness: Optional[str],
    ) -> WebSearchResponse:
        params: dict[str, Any] = {
            "q": query,
            "country": country,
            "search_lang": language,
            "count": count,
            "offset": offset,
        }
        if freshness:
            params["freshness"] = freshness  # pd/tf/year/month/week/day accepted
        try:
            with self._client() as client:
                response = client.get(_BRAVE_WEB_SEARCH_URL, params=params)
        except httpx.TimeoutException as exc:
            raise WebSearchTimeoutError("Web search provider timed out.") from exc
        except httpx.TransportError as exc:
            raise WebSearchUnavailableError("Web search provider is unreachable.") from exc

        if response.status_code in (401, 403):
            raise WebSearchAuthenticationError(
                "Web search provider rejected the API key (401/403)."
            )
        if response.status_code == 429:
            retry_after = None
            header = response.headers.get("Retry-After")
            if header:
                try:
                    retry_after = float(header)
                except ValueError:
                    retry_after = None
                if retry_after is None:
                    retry_after = 1.0
            raise WebSearchRateLimitError(
                "Web search provider is rate limiting requests.", retry_after=retry_after
            )
        if response.status_code in (500, 502, 503, 504):
            raise WebSearchUnavailableError(
                f"Web search provider returned HTTP {response.status_code}."
            )
        if response.status_code >= 400:
            raise WebSearchInternalError(
                f"Web search provider returned HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise WebSearchInternalError(
                "Web search provider returned a malformed response."
            ) from exc
        return self._normalize(payload, query, count, offset)

    @staticmethod
    def _normalize(payload: dict[str, Any], query: str, count: int, offset: int) -> WebSearchResponse:
        web = payload.get("web") or {}
        rows = web.get("results") or []
        if not isinstance(rows, list):
            raise WebSearchInternalError("Web search provider returned an invalid result list.")

        results: list[WebSearchResult] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            url = (row.get("url") or "").strip()
            if not url:
                continue
            # Validate + normalize the URL; drop dangerous/malformed entries.
            try:
                url = validate_result_url(url)
            except Exception:
                continue
            domain = _parse_domain(url)
            profile = row.get("profile") if isinstance(row.get("profile"), dict) else {}
            thumbnail = row.get("thumbnail") if isinstance(row.get("thumbnail"), dict) else {}
            results.append(WebSearchResult(
                id=_short_id(url, index),
                title=(row.get("title") or "").strip()[:500],
                url=url,
                domain=domain,
                description=(row.get("description") or "").strip() or None,
                source_name=profile.get("name") or profile.get("long_name") or None,
                page_age=row.get("page_age") or row.get("age") or None,
                page_fetched=_parse_page_fetched(row.get("page_fetched")),
                thumbnail_url=thumbnail.get("src"),
                language=row.get("language") or None,
                is_live=True,
                schemas=[],
                raw_metadata={k: v for k, v in row.items() if k not in ("title", "url", "description")},
                provider=_BRAVE_PROVIDER_NAME,
            ))

        total = 0
        try:
            total = int(web.get("total_results") or 0)
        except (TypeError, ValueError):
            total = len(results)
        more = total > (offset + len(results))
        return WebSearchResponse(
            results=results,
            total_results=max(total, len(results)),
            more_results_available=more,
            next_offset=(offset + len(results)) if more else None,
            provider=_BRAVE_PROVIDER_NAME,
        )

    def health(self):
        return self._status
