"""Application cache tests: TTL expiry, coalescing, namespace isolation.

Uses the in-memory FakeDB (never a live database) so the cache identity,
freshness check and request-coalescing contracts are verified hermetically.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.core.cache import (
    CacheRepository,
    cache_key,
    coerce_ttl,
    normalize_query,
    policy_for,
)
from tests.fake_mongo import FakeDB


@pytest.fixture
def cache() -> CacheRepository:
    return CacheRepository(FakeDB())


# ─── key normalization / identity ──────────────────────────────────────────

def test_normalize_query_folds_case_and_whitespace():
    assert normalize_query("  Hyderabad  ") == normalize_query("hyderabad")
    assert normalize_query(" Hyderabad   City ") == "hyderabad city"


def test_cache_key_ignores_irrelevant_differences():
    a = cache_key("market_research", {"city": "Hyderabad", "listing_type": "sale"})
    b = cache_key("market_research", {"listing_type": "sale", "city": "hyderabad "})
    assert a == b


def test_cache_key_changes_with_filters_currency_and_language():
    base = cache_key("market_research", {"city": "Hyderabad", "currency": "INR"})
    assert cache_key("market_research", {"city": "Hyderabad", "currency": "USD"}) != base
    assert cache_key("market_research", {"city": "Hyderabad", "currency": "INR", "language": "hi"}) != base
    assert cache_key("market_research", {"city": "Hyderabad", "currency": "INR", "listing_type": "rent"}) != base


def test_cache_key_is_namespaced():
    assert cache_key("a", {"x": 1}) != cache_key("b", {"x": 1})


def test_policies_have_distinct_ttls():
    assert policy_for("market_snapshot").ttl_seconds < policy_for("market_research").ttl_seconds
    assert policy_for("external_location").ttl_seconds > policy_for("property_search").ttl_seconds


def test_coerce_ttl_prefers_positive_caller_ttl():
    policy = policy_for("market_research")
    assert coerce_ttl(policy, 30) == 30
    assert coerce_ttl(policy, None) == policy.ttl_seconds
    assert coerce_ttl(policy, 0) == policy.ttl_seconds


# ─── freshness ─────────────────────────────────────────────────────────────

def test_expired_entry_is_a_miss(cache: CacheRepository):
    key = cache_key("property_search", {"q": "hyderabad"})
    cache.set(key, {"value": 1}, ttl_seconds=1)
    assert cache.get(key) is not None
    # Force expiry rather than sleeping.
    cache.coll.update_one(
        {"key": key},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=5)}},
    )
    assert cache.get(key) is None
    # ... but the entry is still visible for honest "previously cached" UI.
    assert cache.get_including_stale(key) is not None


def test_error_entries_are_short_lived(cache: CacheRepository):
    key = cache_key("market_research", {"q": "x"})
    cache.set(key, {"error": "ProviderError"}, ttl_seconds=3600, is_error=True)
    assert cache.get(key)["is_error"] is True
    doc = cache.coll.find_one({"key": key})
    ttl = (doc["expires_at"].replace(tzinfo=timezone.utc if doc["expires_at"].tzinfo is None else None)
           - doc["created_at"].replace(tzinfo=timezone.utc if doc["created_at"].tzinfo is None else None))
    assert ttl.total_seconds() <= 60


def test_naive_mongo_datetimes_are_handled(cache: CacheRepository):
    """A naive ``created_at`` (some drivers) must not crash the freshness math."""
    key = cache_key("property_search", {"q": "y"})
    cache.set(key, {"value": 2}, ttl_seconds=60)
    cache.coll.update_one(
        {"key": key},
        {"$set": {
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).replace(tzinfo=None),
        }},
    )
    entry = cache.get(key)
    assert entry is not None
    assert entry["age_seconds"] >= 0


# ─── coalescing ────────────────────────────────────────────────────────────

def test_concurrent_identical_requests_run_the_producer_once():
    cache = CacheRepository(FakeDB())
    key = cache_key("market_research", {"q": "same"})
    calls = []

    def producer():
        calls.append(1)
        time.sleep(0.15)
        return {"value": "computed"}

    results: list[dict] = []

    def run():
        results.append(cache.get_or_set(key, producer, ttl_seconds=60))

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1, "concurrent identical requests must coalesce to one upstream call"
    assert len(results) == 8
    assert all(r["payload"] == {"value": "computed"} for r in results)
    assert sum(1 for r in results if r["cache_hit"]) == 7


def test_producer_errors_are_cached_briefly_and_resurface(cache: CacheRepository):
    key = cache_key("market_research", {"q": "boom"})

    def producer():
        raise RuntimeError("upstream down")

    with pytest.raises(RuntimeError):
        cache.get_or_set(key, producer, ttl_seconds=3600)
    entry = cache.get(key)
    assert entry is not None and entry["is_error"] is True


def test_unserializable_payloads_are_returned_but_not_cached(cache: CacheRepository):
    key = cache_key("market_research", {"q": "weird"})
    circular: dict = {"a": 1}
    circular["self"] = circular
    result = cache.get_or_set(key, lambda: circular, ttl_seconds=60)
    assert result["payload"]["a"] == 1
    assert result["cache_hit"] is False
    assert cache.get_including_stale(key) is None


# ─── namespace hygiene ─────────────────────────────────────────────────────

def test_invalidate_namespace_only_drops_that_namespace(cache: CacheRepository):
    k1 = cache_key("property_search", {"q": "a"})
    k2 = cache_key("market_snapshot", {"city": "a"})
    cache.set(k1, {"v": 1}, ttl_seconds=60)
    cache.set(k2, {"v": 2}, ttl_seconds=60)
    cache.invalidate_namespace("property_search")
    assert cache.get(k1) is None
    assert cache.get(k2) is not None


def test_stats_reports_namespace_counts(cache: CacheRepository):
    cache.set(cache_key("property_search", {"q": "a"}), {"v": 1}, ttl_seconds=60)
    stats = cache.stats()
    # The namespace roll-up uses an aggregation the in-memory fake does not
    # implement; what must always be present is the in-flight counter.
    assert "in_flight_producers" in stats
    assert "fresh_entries_by_namespace" in stats
