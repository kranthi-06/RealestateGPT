"""WEB DISCOVERY SERVICE tests: enabled/disabled/not-configured/unavailable
states, cache hit/miss/expiry, stale-cache fallback, bounded provider calls and
idempotent persistence. Uses an in-memory Mongo emulation (no DB required).
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fake_mongo import FakeDB  # noqa: E402

from app.ai.query_parser import parse_query  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.discovery.cache import WebSearchCacheRepository, cache_key_for_intent  # noqa: E402
from app.discovery.service import WebDiscoveryService  # noqa: E402
from app.providers.web_search.models import (  # noqa: E402
    WebSearchResponse,
    WebSearchResult,
    WebSearchUnavailableError,
)


def _result(url: str, title: str = "2 BHK Apartment Gachibowli Hyderabad", description: str = "2 BHK for rent Rs 28000/month 1250 sqft.") -> WebSearchResult:
    return WebSearchResult(
        id="id-" + url[-8:],
        title=title,
        url=url,
        domain="exampleportal.com",
        source_name="ExamplePortal",
        description=description,
        provider="fake",
        retrieved_at=datetime.now(timezone.utc),
    )


class FakeProvider:
    name = "fake_provider"

    def __init__(self, results: list[WebSearchResult] | None = None, error: Exception | None = None):
        self.results = results or []
        self.error = error
        self.calls = 0

    def search(self, query, count=20, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return WebSearchResponse(results=self.results, total_results=len(self.results), provider=self.name)


@pytest.fixture(autouse=True)
def _enable_web_discovery(monkeypatch):
    monkeypatch.setattr(settings, "WEB_DISCOVERY_ENABLED", True)
    original = settings.WEB_SEARCH_MAX_QUERIES
    settings.WEB_SEARCH_MAX_QUERIES = 1
    yield
    settings.WEB_SEARCH_MAX_QUERIES = original


def _service(db, provider):
    return WebDiscoveryService(db, provider_factory=lambda: provider)


def test_disabled_returns_typed_state(monkeypatch):
    monkeypatch.setattr(settings, "WEB_DISCOVERY_ENABLED", False)
    outcome = _service(FakeDB(), FakeProvider()).discover(parse_query("2 BHK Hyderabad"))
    assert outcome.status == "disabled"
    assert outcome.code == "WEB_DISCOVERY_DISABLED"
    assert outcome.cards == []
def test_full_flow_bounded_and_persists():
    db = FakeDB()
    urls = [
        "https://www.exampleportal.com/listings/a-1",
        "https://www.otherportal.com/listings/b-2",
    ]
    provider = FakeProvider(results=[
        _result(urls[0]),
        _result(urls[1], title="2 BHK Flat Kondapur Hyderabad", description="Furnished 2 BHK flat Rs 27500/month."),
    ])
    outcome = _service(db, provider).discover(parse_query("2 BHK for rent in Hyderabad"), max_queries=1)
    assert outcome.status == "available"
    assert outcome.code == "OK"
    assert len(outcome.cards) == 2
    assert provider.calls == 1
    assert db["web_property_discoveries"].count_documents({}) == 2
    assert db["web_search_cache"].count_documents({}) == 1
    assert {c["price"] for c in outcome.cards} == {28000.0, 27500.0}


def test_second_call_is_cache_hit_no_provider_call():
    db = FakeDB()
    urls = ["https://www.exampleportal.com/listings/c-1", "https://www.otherportal.com/listings/d-2"]
    provider = FakeProvider(results=[
        _result(urls[0]),
        _result(urls[1], title="2 BHK Flat Kondapur Hyderabad", description="2 BHK Rs 27500/month."),
    ])
    service = _service(db, provider)
    intent = parse_query("2 BHK for rent in Hyderabad")
    first = service.discover(intent, max_queries=1)
    assert first.cache_hit is False
    second = service.discover(intent, max_queries=1)
    assert second.cache_hit is True
    assert provider.calls == 1
    assert len(second.cards) == 2


def test_persist_is_idempotent():
    db = FakeDB()
    urls = ["https://www.exampleportal.com/listings/e-1"]
    provider = FakeProvider(results=[_result(urls[0])])
    service = _service(db, provider)
    intent = parse_query("2 BHK Hyderabad")
    service.discover(intent, max_queries=1)
    db["web_search_cache"].delete_many({})
    second = service.discover(intent, max_queries=1)
    assert second.status == "available"
    assert db["web_property_discoveries"].count_documents({}) == 1


def test_cache_expiry_forces_refresh():
    db = FakeDB()
    urls = ["https://www.exampleportal.com/listings/f-1"]
    provider = FakeProvider(results=[_result(urls[0])])
    service = _service(db, provider)
    intent = parse_query("2 BHK Hyderabad")
    service.discover(intent, max_queries=1)
    assert provider.calls == 1
    coll = db["web_search_cache"]
    doc = coll.find_one({"cache_key": cache_key_for_intent(intent.model_dump())})
    assert doc is not None
    coll.update_one({"cache_key": doc["cache_key"]}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    service.discover(intent, max_queries=1)
    assert provider.calls == 2


def test_stale_cache_fallback_on_provider_failure():
    db = FakeDB()
    urls = ["https://www.exampleportal.com/listings/g-1"]
    provider = FakeProvider(results=[_result(urls[0])])
    service = _service(db, provider)
    intent = parse_query("2 BHK Hyderabad")
    first = service.discover(intent, max_queries=1)
    assert first.cards
    coll = db["web_search_cache"]
    doc = coll.find_one({})
    coll.update_one({"cache_key": doc["cache_key"]}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    provider.error = WebSearchUnavailableError("down")
    provider.results = []
    second = service.discover(intent, max_queries=1)
    assert second.stale_cache_used is True
    assert second.cards


def test_repository_cleanup():
    from app.discovery.repository import WebDiscoveryRepository

    db = FakeDB()
    coll = db["web_property_discoveries"]
    now = datetime.now(timezone.utc)
    coll.insert_one({"canonical_url": "u1", "expires_at": now - timedelta(hours=1)})
    coll.insert_one({"canonical_url": "u2", "expires_at": now + timedelta(hours=1)})
    removed = WebDiscoveryRepository(db).cleanup()
    assert removed == 1
    assert coll.count_documents({}) == 1


def test_web_search_cache_repository_ttl():
    cache = WebSearchCacheRepository(FakeDB())
    now = datetime.now(timezone.utc)
    cache.coll.insert_one({"cache_key": "expired", "expires_at": now - timedelta(seconds=1)})
    cache.coll.insert_one({"cache_key": "fresh", "expires_at": now + timedelta(seconds=300)})
    assert cache.get("expired") is None
    assert cache.get("fresh") is not None


def test_not_configured_returns_typed_state(monkeypatch):
    from app.providers.web_search.models import WebSearchNotConfiguredError

    def factory():
        raise WebSearchNotConfiguredError("not configured")

    outcome = WebDiscoveryService(FakeDB(), provider_factory=factory).discover(parse_query("2 BHK Hyderabad"))
    assert outcome.status == "not_configured"
    assert outcome.code == "WEB_SEARCH_NOT_CONFIGURED"


def test_provider_unavailable_returns_typed_state(monkeypatch):
    provider = FakeProvider(error=WebSearchUnavailableError("provider down"))
    outcome = _service(FakeDB(), provider).discover(parse_query("2 BHK Hyderabad"))
    assert outcome.status == "unavailable"
    assert outcome.code == "WEB_SEARCH_UNAVAILABLE"
    assert outcome.cards == []
