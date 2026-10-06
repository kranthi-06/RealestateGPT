"""Tavily Search API adapter (authorized Web Search API, not scraping).

Endpoint: ``POST https://api.tavily.com/search``

Requests carry the credential in the server-side ``Authorization: Bearer``
header. Only the backend ever calls Tavily: ``TAVILY_API_KEY`` is read here
and must never be exposed to the browser (never a ``NEXT_PUBLIC_`` variable).

Wire format notes (verified against Tavily's API reference):

* ``max_results`` must be ``1..20``; larger values are rejected with HTTP 400,
  so ``count + offset`` is clamped to that ceiling before the request.
* Tavily exposes **no pagination**: ``offset`` is implemented by asking for
  ``count + offset`` rows and slicing, which is honest (an out-of-range offset
  returns an empty page instead of looping forever).
* ``time_range`` accepts exactly ``day|week|month|year``; anything else is
  dropped rather than forwarded as a 400.
* ``country`` is only meaningful for ``topic=news`` and ``language`` only with
  ``filter_by_language``; neither is expressible for a general property query,
  so both caller arguments are ignored rather than faked.
* HTTP 402 means the monthly free credits are exhausted.

Caller-facing semantics match the other adapters: ``count`` caps how many
already-fetched rows are returned, pagination metadata is derived from the
real result set, and nothing is invented.

Typed failure contract
----------------------
* no API key          -> :class:`WebSearchNotConfiguredError` (never fake results)
* 401 / 403           -> :class:`WebSearchAuthenticationError` (never retried)
* 402 (quota) / 429   -> :class:`WebSearchRateLimitError`
* 500/502/503/504     -> :class:`WebSearchUnavailableError`
* timeout             -> :class:`WebSearchTimeoutError`
* malformed body      -> :class:`WebSearchInternalError`
"""
from __future__ import annotations

import logging
import time
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

_TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_TAVILY_PROVIDER_NAME = "tavily"

#: Tavily's documented ``max_results`` ceiling; a larger request is a HTTP 400.
_TAVILY_MAX_RESULTS_CAP = 20

#: ``PropertyCandidate.page_age`` is declared with ``max_length=100``.
_MAX_PAGE_AGE_LENGTH = 100

#: Freshness vocabulary accepted by the other adapters -> Tavily ``time_range``.
_TIME_RANGE_ALIASES = {
    "pd": "day", "d": "day", "day": "day", "24h": "day", "1d": "day",
    "pw": "week", "w": "week", "week": "week", "7d": "week", "1w": "week",
    "pm": "month", "m": "month", "month": "month", "30d": "month", "1m": "month",
    "py": "year", "y": "year", "year": "year", "1y": "year", "365d": "year",
}

#: Result keys that are large or off by default and must not bloat the cache.
_OMITTED_METADATA = frozenset({"title", "url", "content", "raw_content", "images"})


def _parse_domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host.removeprefix("www.")
    except ValueError:
        return ""


def _short_id(url: str, index: int) -> str:
    return f"tavily-{_parse_domain(url) or 'web'}-{index}"


def _search_depth() -> str:
    depth = (getattr(settings, "TAVILY_SEARCH_DEPTH", "") or "basic").strip().lower()
    return depth if depth in {"basic", "advanced"} else "basic"


def _published_text(raw: Any) -> Optional[str]:
    """Tavily returns ``published_date`` as a date/ISO string; keep it verbatim."""
    if raw is None:
        return None
    text = str(raw).strip()
    return text[:_MAX_PAGE_AGE_LENGTH] if text else None


class TavilySearchProvider(BaseWebSearchProvider):
    """Normalized Tavily web-result adapter (backend-only credential)."""

    name = _TAVILY_PROVIDER_NAME

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__()
        self.api_key = api_key if api_key is not None else settings.TAVILY_API_KEY
        self.circuit = CircuitBreaker()
        self._latency: list[float] = []

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(settings.WEB_SEARCH_TIMEOUT_SECONDS),
            headers={
                # Server-side only; this header never reaches the browser.
                "Authorization": f"Bearer {self.api_key or ''}",
                "Content-Type": "application/json",
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
        if not (self.api_key or "").strip():
            raise WebSearchNotConfiguredError(
                "TAVILY_API_KEY is not configured. Web discovery is unavailable until it is set."
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
        # ``country``/``language`` are accepted by the shared interface but are
        # not expressible on a general Tavily search; they are ignored here
        # instead of being forwarded as an invalid combination.
        _ = country, language

        body: dict[str, Any] = {
            "query": query,
            "max_results": max(1, min(count + offset, _TAVILY_MAX_RESULTS_CAP)),
            "search_depth": _search_depth(),
            "topic": "general",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        time_range = _TIME_RANGE_ALIASES.get((freshness or "").strip().lower())
        if time_range:
            body["time_range"] = time_range

        try:
            with self._client() as client:
                response = client.post(_TAVILY_SEARCH_URL, json=body)
        except httpx.TimeoutException as exc:
            raise WebSearchTimeoutError("Tavily request timed out.") from exc
        except httpx.RequestError as exc:
            # Base class for every transport failure (DNS, TLS, reset, ...).
            raise WebSearchUnavailableError("Tavily is unreachable.") from exc

        if response.status_code in (401, 403):
            raise WebSearchAuthenticationError("Tavily rejected the API key (401/403).")
        if response.status_code == 402:
            raise WebSearchRateLimitError(
                "Tavily free-tier quota is exhausted; web discovery resumes when "
                "the monthly credits reset.",
                retry_after=None,
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
                "Tavily is rate limiting requests.", retry_after=retry_after
            )
        if response.status_code in (500, 502, 503, 504):
            raise WebSearchUnavailableError(f"Tavily returned HTTP {response.status_code}.")
        if response.status_code == 400:
            raise WebSearchInvalidRequestError(
                "Tavily rejected the search request (HTTP 400)."
            )
        if response.status_code >= 400:
            raise WebSearchInternalError(f"Tavily returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise WebSearchInternalError("Tavily returned a malformed response.") from exc
        if not isinstance(payload, dict):
            raise WebSearchInternalError("Tavily returned a malformed response.")
        return self._normalize(payload, count, offset)

    @staticmethod
    def _normalize(payload: dict[str, Any], count: int, offset: int) -> WebSearchResponse:
        rows = payload.get("results")
        if not isinstance(rows, list):
            raise WebSearchInternalError("Tavily returned an invalid result list.")

        page = rows[offset:offset + count] if offset < len(rows) else []
        results: list[WebSearchResult] = []
        for index, row in enumerate(page, start=offset):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            if not title or not url:
                continue
            # Defense-in-depth: drop dangerous/malformed URLs (javascript:,
            # data:, SSRF targets, embedded credentials, ...).
            try:
                url = validate_result_url(url)
            except Exception:
                continue
            domain = _parse_domain(url)
            if not domain:
                continue
            content = row.get("content")
            description = str(content).strip() if content else None
            results.append(WebSearchResult(
                id=_short_id(url, index),
                title=title[:500],
                url=url,
                domain=domain,
                description=description,
                # The real source of a Tavily hit is the site that published it.
                source_name=domain,
                page_age=_published_text(row.get("published_date")),
                # ``published_date`` is a publication date, not a fetch time, so
                # ``page_fetched`` stays None and freshness falls back to
                # ``discovered_at`` rather than claiming a fetch that never happened.
                page_fetched=None,
                thumbnail_url=None,
                language=None,
                is_live=True,
                schemas=[],
                raw_metadata={
                    key: value for key, value in row.items()
                    if key not in _OMITTED_METADATA
                },
                provider=_TAVILY_PROVIDER_NAME,
            ))

        more_available = len(rows) > (offset + len(page))
        return WebSearchResponse(
            results=results,
            total_results=max(len(rows), len(results)),
            more_results_available=more_available,
            next_offset=(offset + len(page)) if more_available else None,
            provider=_TAVILY_PROVIDER_NAME,
        )

    def health(self):
        return self._status
