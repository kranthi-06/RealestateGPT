"""Tavily provider tests: request contract, normalization, typed failures,
credential isolation and registry/config wiring. No real provider calls happen.
"""
from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings, settings
from app.providers.web_search.models import (
    WebSearchAuthenticationError,
    WebSearchInternalError,
    WebSearchInvalidRequestError,
    WebSearchNotConfiguredError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
    WebSearchUnavailableError,
)
from app.providers.web_search.tavily import TavilySearchProvider

VALID_PAYLOAD = {
    "query": "2 bhk rent hyderabad",
    "results": [
        {
            "title": "2 BHK Apartment for Rent in Gachibowli, Hyderabad",
            "url": "https://www.exampleportal.com/listings/2bhk-gachibowli-123",
            "content": "2 BHK semi-furnished apartment for rent near the metro.",
            "score": 0.91,
            "published_date": "2026-09-28",
        },
        {
            "title": "3 BHK House in Kondapur",
            "url": "https://magicbricks.com/property/3bhk-kondapur-9",
            "content": "Spacious 3 BHK independent house.",
            "score": 0.87,
        },
    ],
    "response_time": 1.42,
    "usage": {"credits": 1},
}


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeClient:
    """Stands in for httpx.Client and records every POST the provider sends."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.error is not None:
            raise self.error
        return self.response


def make_provider(response=None, api_key="tvly-test-key", error=None):
    provider = TavilySearchProvider(api_key=api_key)
    fake = FakeClient(response=response, error=error)
    provider._client = lambda: fake
    return provider, fake


@pytest.fixture(autouse=True)
def _no_retries(monkeypatch):
    """Fail fast in unit tests; retry behaviour lives in test_web_search_providers."""
    monkeypatch.setattr(settings, "WEB_SEARCH_MAX_RETRIES", 0)


def test_tavily_not_configured_raises_typed_error(monkeypatch):
    # ``api_key=None`` means "read from settings", so settings must be cleared
    # explicitly — otherwise a developer ``.env`` would turn this into a live call.
    monkeypatch.setattr(settings, "TAVILY_API_KEY", None)
    provider = TavilySearchProvider()
    with pytest.raises(WebSearchNotConfiguredError) as excinfo:
        provider.search("2 BHK Hyderabad")
    assert excinfo.value.code == "WEB_SEARCH_NOT_CONFIGURED"


def test_tavily_blank_key_is_not_configured():
    provider = TavilySearchProvider(api_key="   ")
    with pytest.raises(WebSearchNotConfiguredError):
        provider.search("2 BHK Hyderabad")


def test_tavily_successful_response_and_normalization():
    provider, _ = make_provider(FakeResponse(payload=VALID_PAYLOAD))
    response = provider.search("2 bhk rent hyderabad", count=20)

    assert response.provider == "tavily"
    assert len(response.results) == 2
    first = response.results[0]
    assert first.title.startswith("2 BHK Apartment")
    assert first.url == "https://www.exampleportal.com/listings/2bhk-gachibowli-123"
    assert first.domain == "exampleportal.com"
    assert first.source_name == "exampleportal.com"
    assert first.description.startswith("2 BHK semi-furnished")
    assert first.page_age == "2026-09-28"
    # Publication date must never be reported as a fetch time.
    assert first.page_fetched is None
    assert first.provider == "tavily"
    assert response.total_results == 2
    assert response.more_results_available is False
    assert response.next_offset is None


def test_tavily_request_body_contract():
    """Documented Tavily vocabulary: clamped max_results, no unsupported fields."""
    provider, fake = make_provider(FakeResponse(payload=VALID_PAYLOAD))
    provider.search("2 bhk rent hyderabad", count=20, offset=0, freshness="pw")

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://api.tavily.com/search"
    body = call["json"]
    assert body["query"] == "2 bhk rent hyderabad"
    # Tavily rejects max_results > 20 with HTTP 400.
    assert body["max_results"] == 20
    assert body["search_depth"] in {"basic", "advanced"}
    assert body["topic"] == "general"
    assert body["include_answer"] is False
    assert body["include_raw_content"] is False
    assert body["include_images"] is False
    assert body["time_range"] == "week"
    # country/language are not expressible on a general search -> never sent.
    assert "country" not in body
    assert "language" not in body


def test_tavily_max_results_clamped_to_provider_ceiling(monkeypatch):
    monkeypatch.setattr(settings, "WEB_SEARCH_MAX_RESULTS", 50)
    provider, fake = make_provider(FakeResponse(payload=VALID_PAYLOAD))
    provider.search("query", count=50, offset=10)
    assert fake.calls[0]["json"]["max_results"] == 20


def test_tavily_ignores_unknown_freshness():
    provider, fake = make_provider(FakeResponse(payload=VALID_PAYLOAD))
    provider.search("query", freshness="whenever")
    assert "time_range" not in fake.calls[0]["json"]


def test_tavily_empty_query_is_rejected():
    provider, _ = make_provider(FakeResponse(payload=VALID_PAYLOAD))
    with pytest.raises(WebSearchInvalidRequestError):
        provider.search("   ")


def test_tavily_timeout_raises_typed_error():
    provider, _ = make_provider(error=httpx.TimeoutException("timed out"))
    with pytest.raises(WebSearchTimeoutError):
        provider.search("test")


def test_tavily_transport_failure_raises_unavailable():
    provider, _ = make_provider(error=httpx.ConnectError("dns down"))
    with pytest.raises(WebSearchUnavailableError):
        provider.search("test")


def test_tavily_401_is_authentication_error_and_is_not_retried(monkeypatch):
    monkeypatch.setattr(settings, "WEB_SEARCH_MAX_RETRIES", 3)
    provider, fake = make_provider(FakeResponse(status_code=401, payload={"detail": "bad key"}))
    with pytest.raises(WebSearchAuthenticationError):
        provider.search("test")
    assert len(fake.calls) == 1


def test_tavily_402_reports_exhausted_free_quota():
    provider, fake = make_provider(FakeResponse(status_code=402, payload={"detail": "no credits"}))
    with pytest.raises(WebSearchRateLimitError) as excinfo:
        provider.search("test")
    assert "quota" in excinfo.value.message
    assert len(fake.calls) == 1


def test_tavily_429_honours_retry_after():
    provider, _ = make_provider(FakeResponse(status_code=429, headers={"Retry-After": "7"}))
    with pytest.raises(WebSearchRateLimitError) as excinfo:
        provider.search("test")
    assert excinfo.value.retry_after == 7.0


def test_tavily_5xx_raises_unavailable():
    provider, _ = make_provider(FakeResponse(status_code=503, payload={}))
    with pytest.raises(WebSearchUnavailableError):
        provider.search("test")


def test_tavily_400_raises_invalid_request():
    provider, _ = make_provider(FakeResponse(status_code=400, payload={}))
    with pytest.raises(WebSearchInvalidRequestError):
        provider.search("test")


def test_tavily_malformed_json():
    class BadJSON(FakeResponse):
        def json(self):
            raise ValueError("Invalid JSON")

    provider, _ = make_provider(BadJSON())
    with pytest.raises(WebSearchInternalError, match="malformed"):
        provider.search("test")


def test_tavily_invalid_results_list():
    provider, _ = make_provider(FakeResponse(payload={"results": "oops"}))
    with pytest.raises(WebSearchInternalError, match="invalid result list"):
        provider.search("test")


def test_tavily_empty_results():
    provider, _ = make_provider(FakeResponse(payload={"results": []}))
    response = provider.search("nothing here")
    assert response.results == []
    assert response.more_results_available is False
    assert response.total_results == 0


def test_tavily_drops_dangerous_urls():
    payload = {"results": [
        {"title": "bad", "url": "javascript:alert(1)"},
        {"title": "local", "url": "http://127.0.0.1/x"},
        {"title": "creds", "url": "https://user:pass@example.com/a"},
        {"title": "good", "url": "https://safe.test/property/1"},
        {"title": "no url", "content": "x"},
    ]}
    provider, _ = make_provider(FakeResponse(payload=payload))
    response = provider.search("test")
    assert len(response.results) == 1
    assert response.results[0].title == "good"


def test_tavily_offset_slices_the_real_page():
    """Tavily has no paging: offset slices the rows it really returned."""
    payload = {"results": [
        {"title": f"R{i}", "url": f"https://site{i}.test/p/{i}"} for i in range(5)
    ]}
    provider, fake = make_provider(FakeResponse(payload=payload))

    page = provider.search("test", count=2, offset=4)
    assert [r.title for r in page.results] == ["R4"]
    assert page.more_results_available is False
    assert page.next_offset is None
    # count + offset is requested, still inside the provider ceiling.
    assert fake.calls[0]["json"]["max_results"] == 6

    mid = provider.search("test", count=1, offset=1)
    assert [r.title for r in mid.results] == ["R1"]
    assert mid.more_results_available is True
    assert mid.next_offset == 2

    past_end = provider.search("test", count=5, offset=99)
    assert past_end.results == []
    assert past_end.more_results_available is False


def test_tavily_credential_is_sent_only_as_authorization_header():
    """The key must never appear in the URL or the request body."""
    from app.providers.web_search.tavily import _TAVILY_SEARCH_URL

    assert _TAVILY_SEARCH_URL.startswith("https://")

    provider = TavilySearchProvider(api_key="tvly-super-secret")
    client = provider._client()
    try:
        assert client.headers["Authorization"] == "Bearer tvly-super-secret"
        assert "tvly-super-secret" not in str(client.base_url)
    finally:
        client.close()

    fake = FakeClient(response=FakeResponse(payload=VALID_PAYLOAD))
    provider._client = lambda: fake
    provider.search("2 bhk hyderabad")
    call = fake.calls[0]
    assert "tvly-super-secret" not in call["url"]
    assert "tvly-super-secret" not in str(call["json"])


def test_tavily_is_registered_in_the_provider_registry(monkeypatch):
    from app.providers.web_search.registry import get_web_search_provider, registered_providers

    assert "tavily" in registered_providers()
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "tavily")
    provider = get_web_search_provider()
    assert isinstance(provider, TavilySearchProvider)
    assert provider.name == "tavily"


def test_tavily_configuration_state(monkeypatch):
    configured = Settings(WEB_SEARCH_PROVIDER="tavily", TAVILY_API_KEY="tvly-x")
    assert configured.web_search_configured is True

    missing = Settings(WEB_SEARCH_PROVIDER="tavily", TAVILY_API_KEY=None)
    assert missing.web_search_configured is False


def test_tavily_missing_key_warns_in_production_configuration():
    cfg = Settings(
        APP_ENV="production",
        WEB_DISCOVERY_ENABLED=True,
        WEB_SEARCH_PROVIDER="tavily",
        TAVILY_API_KEY=None,
        CRON_SECRET="x" * 20,
        WORKER_RUN_SECRET="y" * 20,
        CORS_ORIGINS="https://realestate-gpt-inky.vercel.app",
    )
    warnings = cfg.configuration_warnings()
    assert any("TAVILY_API_KEY" in w for w in warnings)


def test_tavily_unregistered_provider_message_is_honest():
    from app.providers.web_search.registry import get_web_search_provider
    from app.providers.web_search.models import WebSearchNotConfiguredError

    original = settings.WEB_SEARCH_PROVIDER
    settings.WEB_SEARCH_PROVIDER = "does-not-exist"
    try:
        with pytest.raises(WebSearchNotConfiguredError) as excinfo:
            get_web_search_provider()
        assert "tavily" in excinfo.value.message  # lists registered providers
    finally:
        settings.WEB_SEARCH_PROVIDER = original
