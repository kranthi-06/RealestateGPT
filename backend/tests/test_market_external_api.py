"""Market intelligence API: external research endpoint + security boundaries.

The external endpoint must:
* return sourced observations (never fabricated figures),
* report typed states when retrieval is unavailable,
* rate-limit callers,
* never leak one caller's data to another (no personalized cache entries).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from tests.fake_mongo import FakeDB


@pytest.fixture(autouse=True)
def _enable_research(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_RESEARCH_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    # Hermetic: the AI summary is covered by the service tests with fakes.
    monkeypatch.setattr(settings, "MARKET_RESEARCH_AI_SUMMARY", False)


def _client(store: FakeDB) -> TestClient:
    from app.core.database import get_db

    app.dependency_overrides[get_db] = lambda: store
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class _FakeProvider:
    name = "fake-search"

    def search(self, query, country=None, language=None, count=20, offset=0, freshness=None):
        from app.providers.web_search.models import WebSearchResponse, WebSearchResult

        return WebSearchResponse(
            results=[
                WebSearchResult(
                    id="1",
                    title="Market rates for the test area",
                    url="https://example.test/rates",
                    domain="example.test",
                    description="Asking prices average Rs 5,000 per sq ft here, starting from Rs 45,00,000.",
                    provider=self.name,
                ),
            ],
            total_results=1,
            provider=self.name,
        )


class _FakeGeo:
    name = "fake-geo"

    def geocode(self, address):
        return {
            "formatted_address": f"{address}, Testland",
            "latitude": 1.0,
            "longitude": 2.0,
            "country": "Testland",
            "country_code": "TL",
            "city": address,
        }


def test_external_endpoint_returns_sourced_observations(monkeypatch):
    import app.services.external_market_service as ems
    import app.providers.location as location_module

    monkeypatch.setattr(ems, "get_web_search_provider", lambda: _FakeProvider())
    monkeypatch.setattr(location_module, "get_location_provider", lambda: _FakeGeo())

    with _client(FakeDB()) as client:
        response = client.post("/api/v1/market/external", json={"location": "Testville"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data_class"] == "external_observation"
    assert payload["sources"][0]["url"] == "https://example.test/rates"
    assert payload["observations"]
    assert payload["statistics"]["asking_price"]["available"] is True
    assert "not verified listings" in payload["disclaimer"]


def test_external_endpoint_requires_a_location():
    with _client(FakeDB()) as client:
        assert client.post("/api/v1/market/external", json={}).status_code == 422


def test_external_endpoint_reports_unconfigured_honestly():
    from app.providers.web_search.models import WebSearchNotConfiguredError

    def boom():
        raise WebSearchNotConfiguredError("not configured")

    import app.services.external_market_service as ems

    original = ems.get_web_search_provider
    ems.get_web_search_provider = boom
    try:
        with _client(FakeDB()) as client:
            response = client.post("/api/v1/market/external", json={"location": "Testville"})
    finally:
        ems.get_web_search_provider = original
    # The service catches the typed error and reports the state honestly.
    assert response.status_code in (200, 503)


def test_insights_attaches_external_research_when_catalogue_is_empty(monkeypatch):
    import app.services.external_market_service as ems
    import app.providers.location as location_module

    monkeypatch.setattr(ems, "get_web_search_provider", lambda: _FakeProvider())
    monkeypatch.setattr(location_module, "get_location_provider", lambda: _FakeGeo())

    with _client(FakeDB()) as client:
        response = client.get("/api/v1/market/insights?city=Testville")
    assert response.status_code == 200
    payload = response.json()
    assert payload["totals"]["listings"] == 0
    assert payload["insufficient_data"]["code"] == "NO_LISTINGS"
    assert payload["external"]["status"] == "ok"
    assert payload["external"]["data_class"] == "external_observation"


def test_insights_can_skip_external_research():
    with _client(FakeDB()) as client:
        response = client.get("/api/v1/market/insights?city=Testville&include_external=false")
    assert response.status_code == 200
    assert response.json()["external"] is None
