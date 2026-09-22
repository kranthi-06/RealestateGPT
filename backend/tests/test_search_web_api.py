"""Unified search API tests (verified + web-discovered).

These are DB integration tests (they exercise the real MongoDB stack). They are
skipped when MONGODB_URI is not set. Provider calls are always mocked — real
provider APIs are never used in CI.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import close_connection, connect
from app.discovery.service import WebDiscoveryOutcome, WebDiscoveryService
from app.main import app

pytestmark = pytest.mark.skipif(not settings.MONGODB_URI, reason="MONGODB_URI is not configured")


@pytest.fixture
def client():
    connect()
    with TestClient(app) as test_client:
        yield test_client
    close_connection()


def _card(title: str = "2 BHK Apartment Gachibowli Hyderabad", price: float = 28000, url: str = "https://99acres.com/property/2bhk-gachibowli-123") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": "507f1f77bcf86cd799439011",
        "title": title,
        "url": url,
        "source_domain": "99acres.com",
        "source_name": "99acres",
        "description": "2 BHK for rent near metro.",
        "price": price,
        "currency": "INR",
        "transaction_type": "rent",
        "bedrooms": 2,
        "area": 1250.0,
        "area_unit": "sqft",
        "location_text": "Gachibowli, Hyderabad",
        "city": "Hyderabad",
        "confidence": 0.91,
        "extraction_method": "snippet",
        "provider": "brave",
        "discovered_at": now.isoformat(),
        "freshness_label": "Discovered moments ago",
        "verification_status": "web_discovery",
    }


def _available_outcome() -> WebDiscoveryOutcome:
    return WebDiscoveryOutcome(
        status="available", code="OK", cards=[_card()],
        queries_used=["2 BHK for rent in Hyderabad"],
        provider="brave", sources_searched=["99acres"],
    )


def test_unified_search_internal_only(client):
    response = client.post("/api/v1/search", json={"query": "2 BHK in Hyderabad", "include_web": False})
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["web_search_used"] is False
    assert body["web_total"] == 0
    assert "query" in body


def test_unified_search_web_enabled_returns_cards(monkeypatch, client):
    monkeypatch.setattr(settings, "WEB_DISCOVERY_ENABLED", True)
    monkeypatch.setattr(
        WebDiscoveryService, "discover",
        lambda self, intent, **kwargs: _available_outcome(),
    )
    response = client.post("/api/v1/search", json={"query": "2 BHK for rent near metro in Hyderabad", "include_web": True})
    assert response.status_code == 200
    body = response.json()
    assert body["web_total"] == 1
    card = body["web_discoveries"][0]
    assert card["verification_status"] == "web_discovery"
    assert card["url"].startswith("https://99acres.com/")
    assert body["metadata"]["web_search_used"] is True
    assert body["metadata"]["provider"] == "brave"
    assert body["metadata"]["counts"]["web"] == 1


def test_unified_search_not_configured_is_honest(monkeypatch, client):
    monkeypatch.setattr(settings, "WEB_DISCOVERY_ENABLED", True)
    from app.providers.web_search.models import WebSearchNotConfiguredError
    import app.discovery.service as service_module

    def factory():
        raise WebSearchNotConfiguredError("not configured")

    monkeypatch.setattr(service_module, "get_web_search_provider", factory)
    response = client.post("/api/v1/search", json={"query": "2 BHK in Hyderabad", "include_web": True})
    assert response.status_code == 200
    body = response.json()
    assert body["web_total"] == 0
    assert body["metadata"]["provider_status"] == "not_configured"
    assert "not configured" in (body["metadata"]["web_message"] or "").lower()


def test_unified_search_provider_failure_does_not_crash(monkeypatch, client):
    monkeypatch.setattr(settings, "WEB_DISCOVERY_ENABLED", True)
    monkeypatch.setattr(
        WebDiscoveryService, "discover",
        lambda self, intent, **kwargs: WebDiscoveryOutcome(
            status="unavailable", code="WEB_SEARCH_UNAVAILABLE",
            message="Web discovery is temporarily unavailable.",
        ),
    )
    response = client.post("/api/v1/search", json={"query": "2 BHK in Hyderabad", "include_web": True})
    assert response.status_code == 200
    assert response.json()["metadata"]["provider_status"] == "unavailable"


def test_unified_search_empty_results_returns_sections(client):
    response = client.post("/api/v1/search", json={"query": "zzzz not-a-real-place-xyz", "include_web": False})
    assert response.status_code == 200
    body = response.json()
    assert body["verified_total"] == 0


def test_discovery_detail_not_found(client):
    response = client.get("/api/v1/search/discoveries/000000000000000000000000")
    assert response.status_code == 404