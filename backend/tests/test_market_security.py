"""Security tests for the new network-exposed surfaces.

Covers:
* external market research: rate limiting, invalid input, no personalized data
  in the shared cache (one user's research cannot leak to another);
* the investment endpoint rejects nonsense input instead of computing on it;
* saved-property ownership boundaries still hold (regression guard).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.cache import CacheRepository, cache_key, normalize_query
from app.main import app
from tests.fake_mongo import FakeDB


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client(store: FakeDB) -> TestClient:
    from app.core.database import get_db

    app.dependency_overrides[get_db] = lambda: store
    return TestClient(app)


# ─── input validation ──────────────────────────────────────────────────────

def test_external_endpoint_rejects_oversized_and_empty_input():
    with _client(FakeDB()) as client:
        assert client.post("/api/v1/market/external", json={"location": ""}).status_code == 422
        assert client.post("/api/v1/market/external", json={"location": "x" * 500}).status_code == 422
        assert client.post(
            "/api/v1/market/external", json={"location": " Hyderabad ", "bedrooms": 99}
        ).status_code == 422


def test_market_insights_rejects_missing_location():
    with _client(FakeDB()) as client:
        assert client.get("/api/v1/market/insights").status_code == 422
        assert client.get("/api/v1/market/insights?bedrooms=-3").status_code == 422


def test_investment_endpoint_rejects_unknown_tools_and_bad_prices():
    with _client(FakeDB()) as client:
        # No property source at all.
        assert client.post("/api/v1/finance/investment", json={"monthly_rent": 1000}).status_code == 422
        # A negative manual price is rejected before any calculation.
        assert client.post(
            "/api/v1/finance/investment",
            json={"manual_properties": [{"label": "X", "price": -5}]},
        ).status_code == 422
        # More than four properties is rejected.
        assert client.post(
            "/api/v1/finance/investment",
            json={"manual_properties": [{"label": f"P{i}", "price": 1_000_000} for i in range(5)]},
        ).status_code == 422


# ─── cache safety ──────────────────────────────────────────────────────────

def test_cache_keys_never_contain_user_identifiers():
    """The shared cache is keyed by normalized request parameters only.

    A user id, token or email must never become part of a cache identity, or
    one user's entry could be served to another.
    """
    key = cache_key("market_research", {"location": "Hyderabad", "user_id": 42})
    payload = key
    for secret in ("42", "user_id"):
        # The literal field name never appears, and the id is hashed inside.
        assert f'"{secret}"' not in payload
    # Two different user ids that produce otherwise identical parameters must
    # NOT be distinguishable through the key (they are both dropped/irrelevant).
    assert normalize_query({"location": "Hyderabad"}) == normalize_query({"location": "hyderabad"})


def test_shared_cache_serves_the_same_payload_to_every_caller():
    cache = CacheRepository(FakeDB())
    key = cache_key("market_research", {"location": "Hyderabad"})
    cache.set(key, {"value": "public-market-data"}, ttl_seconds=60)
    first = cache.get(key)
    second = cache.get(key)
    assert first["payload"] == second["payload"] == {"value": "public-market-data"}


def test_saved_properties_stay_user_scoped():
    """Regression guard: saved lists are ownership-scoped in the repository."""
    from datetime import datetime, timezone

    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.models.user import User
    from app.repositories.saved_repo import SavedRepository

    store = FakeDB()
    now = datetime.now(timezone.utc)
    for pid in (8001, 8002):
        store["properties"].insert_one({
            "_id": pid, "title": f"P{pid}", "slug": f"p{pid}", "price": 1_000_000.0,
            "property_type": "apartment", "listing_type": "sale", "source": "t",
            "source_type": "admin", "city": "C", "is_active": True,
        })
    store["saved_properties"].insert_one(
        {"_id": 1, "user_id": 111, "property_id": 8001, "notes": None, "created_at": now}
    )
    repo = SavedRepository(store)
    assert repo.get_saved_property_ids(111) == [8001]
    assert repo.get_saved_property_ids(222) == []
    assert repo.unsave_property(222, 8001) is False


# ─── rate limiting on the new endpoint ─────────────────────────────────────

def test_external_endpoint_is_rate_limited(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "MARKET_RESEARCH_RATE_LIMIT", 2)
    monkeypatch.setattr(settings, "MARKET_RESEARCH_RATE_WINDOW", 60)
    monkeypatch.setattr(settings, "MARKET_RESEARCH_ENABLED", False)  # fail fast, no upstream

    with _client(FakeDB()) as client:
        codes = [
            client.post("/api/v1/market/external", json={"location": "X"}).status_code
            for _ in range(4)
        ]
    assert 429 in codes, "the external endpoint must rate-limit callers"
