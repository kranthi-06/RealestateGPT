"""WEB SEARCH provider tests: successful request, timeouts, 429/401/403/500,
malformed responses, empty results, pagination metadata, retry policy and the
circuit breaker. No real provider calls ever happen.
"""
from __future__ import annotations

import time

import httpx
import pytest

from app.providers.web_search.brave import BraveSearchProvider
from app.providers.web_search.circuit_breaker import CircuitBreaker
from app.providers.web_search.models import (
    WebSearchAuthenticationError,
    WebSearchInvalidRequestError,
    WebSearchNotConfiguredError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
    WebSearchUnavailableError,
)
from app.providers.web_search.retry import is_retryable_error, retry_with_backoff


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse):
        self._response = response
        self.last_params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, params=None):
        self.last_params = params
        return self._response


VALID_PAYLOAD = {
    "web": {
        "results": [
            {
                "title": "2 BHK Apartment in Gachibowli, Hyderabad",
                "url": "https://www.exampleportal.com/listings/2bhk-gachibowli-123",
                "description": "2 BHK apartment for rent near metro.",
                "profile": {"name": "ExamplePortal"},
                "language": "en",
                "age": "2 days old",
            }
        ],
        "total_results": 3,
    }
}


def make_provider(monkeypatch, response: FakeResponse, api_key: str = "test-key"):
    provider = BraveSearchProvider(api_key=api_key)
    provider._client = lambda: FakeClient(response)
    return provider


def test_not_configured_raises_typed_error(monkeypatch):
    provider = BraveSearchProvider(api_key=None)
    with pytest.raises(WebSearchNotConfiguredError) as excinfo:
        provider.search("2 BHK Hyderabad")
    assert excinfo.value.code == "WEB_SEARCH_NOT_CONFIGURED"


def test_provider_success_and_normalization(monkeypatch):
    provider = make_provider(monkeypatch, FakeResponse(payload=VALID_PAYLOAD))
    response = provider.search("2 BHK Hyderabad", country="IN", language="en", count=20)
    assert len(response.results) == 1
    result = response.results[0]
    assert result.title.startswith("2 BHK Apartment")
    assert result.domain == "exampleportal.com"
    assert result.source_name == "ExamplePortal"
    assert result.provider == "brave"
    assert result.page_age == "2 days old"
    assert response.more_results_available is True
    assert response.next_offset == 1


def test_provider_timeout_raises_typed_error(monkeypatch):
    provider = BraveSearchProvider(api_key="k")

    def boom(self):
        raise httpx.TimeoutException("timed out")

    provider._client = lambda: type("C", (), {"__enter__": boom, "__exit__": lambda *a: None})()
    with pytest.raises(WebSearchTimeoutError):
        provider.search("test")


def test_provider_429_raises_rate_limit_with_retry_after(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    provider = make_provider(
        monkeypatch, FakeResponse(status_code=429, headers={"Retry-After": "5"})
    )
    with pytest.raises(WebSearchRateLimitError) as excinfo:
        provider.search("test")
    assert excinfo.value.retry_after == 5.0


def test_provider_401_and_403_are_auth_errors(monkeypatch):
    for code in (401, 403):
        provider = make_provider(monkeypatch, FakeResponse(status_code=code))
        with pytest.raises(WebSearchAuthenticationError):
            provider.search("test")


def test_provider_500_raises_unavailable(monkeypatch):
    provider = make_provider(monkeypatch, FakeResponse(status_code=503))
    with pytest.raises(WebSearchUnavailableError):
        provider.search("test")


def test_provider_malformed_response(monkeypatch):
    from app.providers.web_search.models import WebSearchInternalError

    provider = make_provider(monkeypatch, FakeResponse(payload={"web": {"results": "oops"}}))
    with pytest.raises(WebSearchInternalError):
        provider.search("test")


def test_provider_empty_results(monkeypatch):
    provider = make_provider(monkeypatch, FakeResponse(payload={"web": {"results": [], "total_results": 0}}))
    response = provider.search("nothing here")
    assert response.results == []
    assert response.more_results_available is False


def test_provider_drops_dangerous_urls(monkeypatch):
    payload = {"web": {"results": [
        {"title": "bad", "url": "javascript:alert(1)"},
        {"title": "local", "url": "http://127.0.0.1/x"},
        {"title": "good", "url": "https://safe.test/property/1"},
    ], "total_results": 3}}
    provider = make_provider(monkeypatch, FakeResponse(payload=payload))
    response = provider.search("test")
    assert len(response.results) == 1
    assert response.results[0].title == "good"
def test_retry_success_after_transient_failures(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    calls = [0]

    def flaky():
        calls[0] += 1
        if calls[0] < 3:
            raise WebSearchRateLimitError("slow down", retry_after=0)
        return "ok"

    result = retry_with_backoff(flaky, max_retries=4, timeout_seconds=1)
    assert result == "ok"
    assert calls[0] == 3


def test_retry_does_not_retry_auth_errors(monkeypatch):
    calls = [0]

    def bad_key():
        calls[0] += 1
        raise WebSearchAuthenticationError("nope")

    with pytest.raises(WebSearchAuthenticationError):
        retry_with_backoff(bad_key, max_retries=5, timeout_seconds=1)
    assert calls[0] == 1


def test_is_retryable_classification():
    assert is_retryable_error(WebSearchUnavailableError("x")) is True
    assert is_retryable_error(WebSearchRateLimitError("x", retry_after=1)) is True
    assert is_retryable_error(WebSearchTimeoutError("x")) is True
    assert is_retryable_error(WebSearchAuthenticationError("x")) is False
    assert is_retryable_error(WebSearchInvalidRequestError("x")) is False


def test_circuit_breaker_opens_and_half_opens():
    breaker = CircuitBreaker(failure_threshold=2, window_seconds=60, cooldown_seconds=3600)
    assert breaker.allow_request() is True
    breaker.record_failure(WebSearchUnavailableError("boom"))
    breaker.record_failure(WebSearchUnavailableError("boom"))
    assert breaker.state == "open"
    assert breaker.allow_request() is False  # cooldown not elapsed -> blocked


def test_circuit_breaker_half_open_recovers(monkeypatch):
    breaker = CircuitBreaker(failure_threshold=1, window_seconds=60, cooldown_seconds=3600)
    breaker.record_failure(WebSearchUnavailableError("boom"))
    assert breaker.allow_request() is False  # open + cooldown not elapsed
    import time as _time

    # Simulate the cooldown elapsing (well beyond 3600s) -> half-open allowed.
    breaker._opened_at = _time.monotonic() - 3700
    assert breaker.allow_request() is True
    breaker.record_success()
    assert breaker.state == "healthy"


def test_circuit_breaker_reopens_after_half_open_failure(monkeypatch):
    breaker = CircuitBreaker(failure_threshold=1, window_seconds=60, cooldown_seconds=3600)
    breaker.record_failure(WebSearchUnavailableError("boom"))
    import time as _time

    breaker._opened_at = _time.monotonic() - 3700
    assert breaker.allow_request() is True
    breaker.record_failure(WebSearchUnavailableError("boom again"))
    assert breaker._state == "open"
