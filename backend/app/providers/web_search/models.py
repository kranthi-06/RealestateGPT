"""Typed internal models and errors for the web search provider layer.

No provider-specific response structure may escape this layer. Every provider
adapter normalizes into :class:`WebSearchResult` (and pagination metadata via
:class:`WebSearchResponse`), so the discovery pipeline only ever depends on these
shapes.

Typed errors
------------
* ``WebSearchNotConfiguredError``  -> WEB_SEARCH_NOT_CONFIGURED
* ``WebSearchUnavailableError``    -> WEB_SEARCH_UNAVAILABLE
* ``WebSearchRateLimitError``      -> WEB_SEARCH_RATE_LIMITED
* ``WebSearchAuthenticationError`` -> WEB_SEARCH_AUTHENTICATION_FAILED
* ``WebSearchTimeoutError``        -> WEB_SEARCH_TIMEOUT
* ``WebSearchInvalidRequestError`` -> WEB_SEARCH_INVALID_REQUEST
* ``WebSearchInternalError``       -> WEB_SEARCH_PROVIDER_ERROR

The application NEVER fabricates results. Missing configuration and provider
failures surface as typed states that callers render honestly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WebSearchResult(BaseModel):
    """Normalized web search result consumed by property candidate extraction.

    Only fields that can actually be populated from the provider are set;
    everything else stays ``None``. This is the *only* result model the rest of
    the application sees.
    """

    id: str
    title: str
    url: str
    domain: str
    description: Optional[str] = None
    source_name: Optional[str] = None
    page_age: Optional[str] = None          # e.g. "18 years old" as returned
    page_fetched: Optional[datetime] = None  # source page fetch time (when known)
    thumbnail_url: Optional[str] = None
    language: Optional[str] = None
    is_live: bool = True
    schemas: list[dict[str, Any]] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    provider: str = "web"
    retrieved_at: datetime = Field(default_factory=_utcnow)

    @field_validator("url")
    @classmethod
    def _safe_http_url(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) > 2048:
            raise ValueError("url is too long")
        return v


class WebSearchResponse(BaseModel):
    """Normalized provider response with pagination metadata."""

    results: list[WebSearchResult] = Field(default_factory=list)
    total_results: int = 0
    more_results_available: bool = False
    next_offset: Optional[int] = None
    provider: str = "web"
    retrieved_at: datetime = Field(default_factory=_utcnow)


class WebSearchProviderStatus(BaseModel):
    """Provider health state for admin/worker monitoring."""

    status: Literal["healthy", "degraded", "open", "unavailable", "not_configured"] = "not_configured"
    provider: str = "web"
    requests: int = 0
    success: int = 0
    too_many_requests: int = 0
    errors: int = 0
    average_latency_ms: float = 0.0
    cache_hit_rate: float = 0.0
    last_failure_reason: Optional[str] = None
    last_checked_at: Optional[datetime] = None


class WebSearchError(Exception):
    """Base class for typed web search provider errors."""

    code: str = "WEB_SEARCH_ERROR"
    retryable: bool = False
    status_code: int = 502

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class WebSearchNotConfiguredError(WebSearchError):
    """No provider/credential is configured. Never a fake-result fallback."""

    code = "WEB_SEARCH_NOT_CONFIGURED"
    retryable = False
    status_code = 503


class WebSearchUnavailableError(WebSearchError):
    """Provider is reachable but cannot serve a request right now."""

    code = "WEB_SEARCH_UNAVAILABLE"
    retryable = True
    status_code = 503


class WebSearchRateLimitError(WebSearchError):
    """Provider returned 429 (or our own RPM limit was hit)."""

    code = "WEB_SEARCH_RATE_LIMITED"
    retryable = True
    status_code = 429

    def __init__(self, message: str, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class WebSearchAuthenticationError(WebSearchError):
    """401/403 — bad or missing API key. Do NOT retry."""

    code = "WEB_SEARCH_AUTHENTICATION_FAILED"
    retryable = False
    status_code = 502


class WebSearchTimeoutError(WebSearchError):
    """Provider did not answer within WEB_SEARCH_TIMEOUT_SECONDS."""

    code = "WEB_SEARCH_TIMEOUT"
    retryable = True
    status_code = 504


class WebSearchInvalidRequestError(WebSearchError):
    """Malformed request or provider rejects query shape. Do NOT retry."""

    code = "WEB_SEARCH_INVALID_REQUEST"
    retryable = False
    status_code = 422


class WebSearchInternalError(WebSearchError):
    """Provider 5xx or malformed/unparseable response."""

    code = "WEB_SEARCH_PROVIDER_ERROR"
    retryable = True
    status_code = 502


def provider_missing_message(provider: str) -> str:
    """Honest, typed message when the provider is not configured."""
    if provider == "brave":
        return (
            "Web discovery is not configured yet. Set BRAVE_SEARCH_API_KEY "
            "(server-side) and WEB_DISCOVERY_ENABLED=true to enable it."
        )
    return f"Web discovery provider '{provider}' is not configured."