"""Integration contracts for database-first discovery and bounded OSM ranking."""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import close_connection, connect, get_database
from app.models.property import Property
from app.providers.location import LocationProviderUnavailable
from app.repositories.property_repo import PropertyRepository
from app.services.ai_search_service import AiSearchService
from app.main import app

pytestmark = pytest.mark.skipif(not settings.MONGODB_URI, reason="MONGODB_URI is not configured")


@pytest.fixture
def discovery_db():
    connect()
    db = get_database()
    token = uuid4().hex[:10]
    repo = PropertyRepository(db)
    ids = []
    for bedrooms, price in ((3, 8_500_000), (2, 6_000_000)):
        prop = Property(
            title=f"Discovery test {bedrooms} BHK {token}", slug=f"discovery-{bedrooms}-{token}",
            price=price, property_type="apartment", listing_type="sale", bedrooms=bedrooms,
            bathrooms=2, area=1300, city="Hyderabad", locality="HITEC City",
            latitude=17.4435 + bedrooms / 10000, longitude=78.3772 + bedrooms / 10000,
            source="discovery_test", source_type="demo", source_id=f"{token}-{bedrooms}",
            is_synthetic=True, status='active', verification_status="unverified", data_quality_score=90,
        )
        ids.append(repo.create_property(prop).id)
    yield db
    get_database()["properties"].delete_many({"_id": {"$in": ids}})
    close_connection()


def test_database_first_natural_search_and_explainable_ranking(discovery_db, monkeypatch):
    service = AiSearchService(discovery_db)
    monkeypatch.setattr(service, "_location_context", lambda candidates, intent: (
        {candidates[0].id: {"metro": 0.8}}, {}, [], 1.0
    ))
    result = service.search("Find me a 3BHK under 90 lakhs near metro in Hyderabad")

    assert result["total"] >= 1
    assert result["parsed"].max_price == 9_000_000
    assert result["results"][0].bedrooms == 3
    assert any("Within requested budget" == reason for reason in result["results"][0].positive_factors)
    assert result["metrics"]["candidate_count"] <= 30


def test_location_provider_failure_returns_warning_not_fake_distance(discovery_db, monkeypatch):
    service = AiSearchService(discovery_db)
    monkeypatch.setattr(service, "_location_context", lambda candidates, intent: ({}, {}, ["Live nearby-place enrichment is temporarily unavailable."], 1.0))
    result = service.search("Find a 3BHK near metro in Hyderabad")

    assert "temporarily unavailable" in result["warning"]
    assert not any("km away" in reason for row in result["results"] for reason in row.positive_factors)


def test_discovery_search_api_returns_typed_intent_and_metrics(discovery_db, monkeypatch):
    monkeypatch.setattr(AiSearchService, "_location_context", lambda self, candidates, intent: ({}, {}, [], 0.0))
    with TestClient(app) as client:
        response = client.post("/api/v1/ai/search", json={"query": "Find a 3BHK under 90 lakh in Hyderabad", "limit": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["parsed"]["bedrooms"] == 3
    assert body["parsed"]["max_price"] == 9_000_000
    assert "database_latency_ms" in body["metrics"]
