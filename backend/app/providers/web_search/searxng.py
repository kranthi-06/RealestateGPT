"""SearXNG search provider implementation.

Queries a self-hosted SearXNG instance through its JSON API
(``GET {SEARXNG_BASE_URL}/search?format=json``) and normalizes the payload into
:class:`WebSearchResponse`. Raw SearXNG result dicts never escape this module.

Wire format notes (verified against the SearXNG search-API docs and source:
``searx/result_types/_base.py`` + ``searx/webadapter.py``):

* SearXNG serializes a result's ``parsed_url`` as a **6-element array**
  (``[scheme, netloc, path, params, query, fragment]``), never as a dict, so the
  domain is derived from ``url`` — the array is only a fallback.
* ``time_range`` accepts exactly ``day|week|month|year``; any other value makes
  the instance answer ``400``. ``freshness`` is therefore mapped (or dropped).
* ``language`` must match ``^[a-z]{2,3}(-[a-zA-Z]{2})?$`` or ``auto``; invalid
  codes are dropped instead of being forwarded as a ``400``.
* ``pageno`` is 1-indexed and must be a positive integer.
* ``format=json`` must be enabled in the instance's ``settings.yml``; otherwise
  the instance answers ``403``.

Caller-facing semantics:

* ``count``   -> caps how many already-fetched results are returned (SearXNG
                 exposes no page-size parameter).
* ``offset``  -> translated to a 1-indexed ``pageno`` (best effort; SearXNG does
                 not report its own page size).
* ``country`` -> not expressible in the SearXNG API; ignored rather than faked.
* pagination  -> ``total_results`` / ``more_results_available`` / ``next_offset``
                 are derived from the instance's ``number_of_results`` when it
                 reports one and from the real result set otherwise. Nothing is
                 invented.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.providers.web_search.base import BaseWebSearchProvider
from app.providers.web_search.models import (
    WebSearchInternalError,
    WebSearchInvalidRequestError,
    WebSearchRateLimitError,
    WebSearchResponse,
    WebSearchResult,
    WebSearchTimeoutError,
)
from app.providers.web_search.registry import web_search_health
from app.providers.web_search.security import validate_result_url

logger = logging.getLogger(__name__)

#: SearXNG validates ``time_range`` against exactly these values.
_VALID_TIME_RANGES = frozenset({"day", "week", "month", "year"})

#: Freshness hints (Brave-style ``pd/pw/pm/py`` plus words) -> ``time_range``.
_FRESHNESS_ALIASES = {
    "pd": "day", "d": "day", "day": "day", "24h": "day", "1d": "day",
    "pw": "week", "w": "week", "week": "week", "7d": "week", "1w": "week",
    "pm": "month", "m": "month", "month": "month", "30d": "month", "1m": "month",
    "py": "year", "y": "year", "year": "year", "1y": "year", "365d": "year",
}

#: Mirrors SearXNG's own validator (``searx/webutils.VALID_LANGUAGE_CODE``).
_VALID_LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}(-[a-zA-Z]{2})?$")


def _parse_domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host.removeprefix("www.")
    except ValueError:
        return ""


def _short_id(url: str, index: int) -> str:
    return f"searxng-{_parse_domain(url) or 'web'}-{index}"


def _normalize_language(raw: Optional[str]) -> Optional[str]:
    """Return a SearXNG-acceptable language code, or ``None`` to omit the param."""
    text = (raw or "").strip().replace("_", "-")
    if not text:
        return None
    if _VALID_LANGUAGE_CODE.match(text):
        return text
    primary = text.split("-", 1)[0].lower()
    if _VALID_LANGUAGE_CODE.match(primary):
        return primary
    logger.debug("SearXNG: ignoring language %r (not a valid language code)", raw)
    return None


def _map_time_range(freshness: Optional[str]) -> Optional[str]:
    """Map a freshness hint onto a valid SearXNG ``time_range`` value."""
    value = (freshness or "").strip().lower()
    if not value:
        return None
    mapped = _FRESHNESS_ALIASES.get(value)
    if mapped is None and value in _VALID_TIME_RANGES:
        mapped = value
    if mapped is None:
        logger.debug("SearXNG: ignoring freshness %r (no matching time_range)", freshness)
    return mapped


def _domain_from_parsed_url(parsed_url: Any) -> str:
    """SearXNG emits ``parsed_url`` as a list; tolerate a dict for older builds."""
    if isinstance(parsed_url, dict):
        netloc = parsed_url.get("netloc") or ""
        return str(netloc).removeprefix("www.")
    if isinstance(parsed_url, (list, tuple)) and len(parsed_url) > 1 and isinstance(parsed_url[1], str):
        return parsed_url[1].removeprefix("www.")
    return ""


def _coerce_int(raw: Any) -> Optional[int]:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _elapsed_ms(response: httpx.Response) -> float:
    """Best-effort latency in ms; never let telemetry break a successful search."""
    try:
        return float(response.elapsed.total_seconds()) * 1000.0
    except Exception:  # pragma: no cover - defensive
        return 0.0


class SearXNGSearchProvider(BaseWebSearchProvider):
    """Normalized SearXNG JSON-API adapter (no API key, self-hosted instance)."""

    name: str = "searxng"

    def search(
        self,
        query: str,
        country: Optional[str] = None,
        language: Optional[str] = None,
        count: int = 20,
        offset: int = 0,
        freshness: Optional[str] = None,
    ) -> WebSearchResponse:
        """Execute a SearXNG search query and normalize the JSON payload."""
        health = web_search_health()
        health.record_start()

        base_url = (settings.SEARXNG_BASE_URL or "").strip()
        if not base_url:
            health.record_error("SEARXNG_BASE_URL not configured")
            raise WebSearchInternalError("SEARXNG_BASE_URL is not configured.")

        query = (query or "").strip()
        if not query:
            health.record_error("Empty query")
            raise WebSearchInvalidRequestError("A search query is required.")

        count = max(1, min(int(count), settings.WEB_SEARCH_MAX_RESULTS))
        offset = max(0, int(offset))

        url = f"{base_url.rstrip('/')}/search"

        # SearXNG pages are 1-indexed and it exposes no page-size parameter, so
        # ``count`` is applied locally to the results of the fetched page.
        page = (offset // count) + 1

        # ``safesearch`` is deliberately not sent: the instance default
        # (search.safe_search in settings.yml) governs it.
        params: dict[str, Any] = {
            "q": query,
            "format": "json",
            "pageno": page,
        }

        resolved_language = _normalize_language(language or settings.WEB_SEARCH_LANGUAGE)
        if resolved_language:
            params["language"] = resolved_language

        # ``country`` has no SearXNG equivalent — it is not faked.
        if country:
            logger.debug("SearXNG: ignoring country hint %r (unsupported by the API)", country)

        time_range = _map_time_range(freshness)
        if time_range:
            params["time_range"] = time_range

        timeout = settings.WEB_SEARCH_TIMEOUT_SECONDS

        # Optional token for a reverse-proxy-protected instance (see
        # SEARXNG_AUTH_TOKEN in config); omitted entirely when unset.
        headers: dict[str, str] = {}
        auth_token = (getattr(settings, "SEARXNG_AUTH_TOKEN", "") or "").strip()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, params=params, headers=headers)

            if response.status_code == 429:
                health.record_rate_limited()
                raise WebSearchRateLimitError("SearXNG rate limit exceeded.")

            if response.status_code == 401:
                health.record_error("HTTP Error: 401")
                raise WebSearchInternalError(
                    "SearXNG rejected the request (HTTP 401). The instance requires a "
                    "bearer token; check that SEARXNG_AUTH_TOKEN matches the proxy."
                )

            if response.status_code == 403:
                # SearXNG answers 403 when the requested format is not enabled.
                health.record_error("HTTP Error: 403")
                raise WebSearchInternalError(
                    "SearXNG returned HTTP error 403. Ensure 'json' is listed under "
                    "search.formats in the instance settings.yml."
                )

            response.raise_for_status()

            try:
                data = response.json()
            except ValueError:
                health.record_error("Invalid JSON response")
                raise WebSearchInternalError("SearXNG returned invalid JSON.")

            if not isinstance(data, dict):
                health.record_error("Unexpected JSON payload type")
                raise WebSearchInternalError("SearXNG returned an unexpected payload.")

            unresponsive = data.get("unresponsive_engines")
            if unresponsive:
                logger.warning("SearXNG reported unresponsive engines: %s", unresponsive)

            result = self._normalize(data, count, offset, resolved_language)
            health.record_success(latency_ms=_elapsed_ms(response))
            return result

        except httpx.TimeoutException:
            health.record_error("Timeout")
            raise WebSearchTimeoutError("SearXNG request timed out.")
        except httpx.HTTPStatusError as e:
            health.record_error(f"HTTP Error: {e.response.status_code}")
            raise WebSearchInternalError(f"SearXNG returned HTTP error {e.response.status_code}.")
        except httpx.RequestError as e:
            health.record_error(f"Request Error: {str(e)}")
            raise WebSearchInternalError(f"SearXNG request failed: {str(e)}")
        except (WebSearchRateLimitError, WebSearchInternalError, WebSearchInvalidRequestError):
            raise
        except Exception as e:  # pragma: no cover - defensive, never fabricate results
            health.record_error(str(e))
            raise WebSearchInternalError(f"SearXNG unexpected error: {str(e)}")

    def _normalize(
        self,
        payload: dict[str, Any],
        count: int,
        offset: int,
        language: Optional[str],
    ) -> WebSearchResponse:
        """Map a SearXNG JSON payload onto the normalized response shape."""
        rows = payload.get("results")
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise WebSearchInternalError("SearXNG returned an invalid result list.")

        results: list[WebSearchResult] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue

            title = str(row.get("title") or "").strip()
            raw_url = str(row.get("url") or "").strip()
            if not title or not raw_url:
                continue

            # Defense-in-depth: drop dangerous/malformed URLs (javascript:,
            # data:, SSRF targets, embedded credentials, ...).
            try:
                url = validate_result_url(raw_url)
            except Exception:
                continue

            domain = _parse_domain(url) or _domain_from_parsed_url(row.get("parsed_url"))
            if not domain:
                continue

            content = row.get("content")
            if isinstance(content, (list, tuple)):
                content = " ".join(str(part) for part in content if part)
            description = str(content).strip() if content else None

            published = row.get("publishedDate") or row.get("pubdate")
            page_fetched = None
            if published:
                try:
                    page_fetched = datetime.fromisoformat(str(published).strip().replace("Z", "+00:00"))
                except (TypeError, ValueError):
                    page_fetched = None

            engines = row.get("engines")
            engine = row.get("engine")
            if not engine and isinstance(engines, (list, tuple, set)):
                engine = ", ".join(sorted(str(item) for item in engines)) or None

            thumbnail = row.get("thumbnail") or row.get("img_src")

            results.append(WebSearchResult(
                id=_short_id(url, index),
                title=title[:500],
                url=url,
                domain=domain,
                description=description,
                source_name=str(engine) if engine else None,
                page_age=str(published) if published else None,
                page_fetched=page_fetched,
                thumbnail_url=str(thumbnail) if thumbnail else None,
                language=row.get("language") or language,
                is_live=True,
                schemas=[],
                raw_metadata={
                    key: value
                    for key, value in row.items()
                    if key not in ("title", "url", "content", "parsed_url")
                },
                provider=self.name,
            ))

        results = results[:count]

        # ``number_of_results`` is only trusted when the instance actually
        # reports a count; otherwise the real result set is the honest total.
        reported_total = _coerce_int(payload.get("number_of_results")) or 0
        more_available = reported_total > (offset + len(results))
        return WebSearchResponse(
            results=results,
            total_results=max(reported_total, len(results)),
            more_results_available=more_available,
            next_offset=(offset + len(results)) if more_available else None,
            provider=self.name,
        )
