"""Integration tests for worker pipeline behavior against MongoDB.

Skipped automatically when MONGODB_URI is not set (same pattern as
test_mongo_integration.py).
"""
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.core.database import close_connection, connect, get_database
from app.services.property_ingestion_service import PropertyIngestionService
from app.repositories.property_repo import PropertyRepository

pytestmark = pytest.mark.skipif(
    not settings.MONGODB_URI, reason="MONGODB_URI is not configured"
)

logger = logging.getLogger(__name__)


@pytest.fixture
def db():
    connect()
    database = get_database()
    yield database
    close_connection()


@pytest.fixture
def clean(db):
    # NOTE: never delete the shared "counters" collection — other test modules
    # depend on monotonic ids for audit_logs etc.
    collections = ("properties", "worker_locks", "worker_runs", "price_history",
                   "geocode_queue", "dedup_reviews")
    for name in collections:
        db[name].delete_many({})
    yield db
    # Teardown: remove the test-created rows so the shared dev database is not
    # littered with fake "active" listings.
    for name in collections:
        db[name].delete_many({})


def _record() -> dict:
    return {
        "source": "test_feed",
        "source_type": "partner_api",
        "source_listing_id": "L-1",
        "title": "3BHK Apartment in HITEC City",
        "price": 7500000,
        "property_type": "apartment",
        "listing_type": "sale",
        "city": "Hyderabad",
        "locality": "HITEC City",
        "bedrooms": 3,
        "bathrooms": 3,
        "area": 1200,
        "area_sqft": 1200,
        "latitude": 17.4435,
        "longitude": 78.3772,
        "address": "HITEC City Main Road, Hyderabad",
    }


class FakeProvider:
    name = "test_feed"
    source_type = "partner_api"

    def __init__(self, records, fail_once: bool = False):
        self.records = list(records)
        self.fail_once = fail_once
        self.refresh_calls: list[str] = []

    async def fetch_properties(self, cursor=None):
        start = int(cursor) if cursor else 0
        batch = self.records[start:start + 10]
        next_cursor = str(start + len(batch)) if start + len(batch) < len(self.records) else None
        return batch, next_cursor

    async def get_property(self, source_listing_id):
        for record in self.records:
            if record["source_listing_id"] == source_listing_id:
                return dict(record)
        return {"source_listing_id": source_listing_id, "status": "inactive"}

    async def refresh(self, source_listing_id):
        self.refresh_calls.append(source_listing_id)
        if self.fail_once:
            self.fail_once = False
            from app.providers.property.errors import ProviderUnavailableError
            raise ProviderUnavailableError("provider down")
        for record in self.records:
            if record["source_listing_id"] == source_listing_id:
                return dict(record)
        from app.providers.property.errors import ProviderListingNotFoundError
        raise ProviderListingNotFoundError("gone")


def _store(clean, record: dict):
    """Store a canonical record through the ingestion service validators."""
    repo = PropertyRepository(clean)
    service = PropertyIngestionService(repo)
    candidate = service.validator.validate(
        service.normalizer.normalize(record, record.get("source"), record.get("source_type"))
    )
    return repo.create_property(candidate)


def test_ingestion_is_idempotent(clean):
    from app.workers.ingestion import run_property_ingestion

    provider = FakeProvider([_record()])
    with patch("app.workers.ingestion.get_property_provider", return_value=provider):
        first = run_property_ingestion(clean, source="test_feed", source_type="partner_api")
        second = run_property_ingestion(clean, source="test_feed", source_type="partner_api")

    assert clean["properties"].count_documents({"source_listing_id": "L-1"}) == 1
    assert first["added"] == 1, first
    assert second["added"] == 0, second  # already seen -> updated, never duplicated
    assert second["updated"] == 1, second

    runs = list(clean["worker_runs"].find({"worker_name": "property_ingestion"}))
    assert len(runs) == 2
    assert runs[0]["status"] == "completed"


def test_ingestion_rejects_bad_records(clean):
    from app.workers.ingestion import run_property_ingestion

    bad = dict(_record(), price=-1)  # price must be > 0
    good = dict(_record())
    provider = FakeProvider([bad, good])
    with patch("app.workers.ingestion.get_property_provider", return_value=provider):
        summary = run_property_ingestion(clean, source="test_feed", source_type="partner_api")

    assert clean["properties"].count_documents({}) == 1
    assert summary["rejected"] == 1, summary


def test_ingestion_queues_geocoding_for_missing_coords(clean):
    from app.workers.ingestion import run_property_ingestion

    without_coords = dict(_record())
    without_coords.pop("latitude")
    without_coords.pop("longitude")
    provider = FakeProvider([without_coords])
    with patch("app.workers.ingestion.get_property_provider", return_value=provider):
        run_property_ingestion(clean, source="test_feed", source_type="partner_api")

    queued = clean["geocode_queue"].find_one({"status": "pending"})
    assert queued is not None
    assert queued["address"] == "HITEC City Main Road, Hyderabad"


def test_refresh_keeps_active_on_provider_failure(clean):
    from app.workers.refresh import run_property_refresh

    prop = _record()
    _store(clean, prop)

    failing = FakeProvider([prop], fail_once=True)
    with patch("app.workers.refresh.get_property_provider", return_value=failing):
        summary = run_property_refresh(clean)

    doc = clean["properties"].find_one({"source_listing_id": "L-1"})
    assert doc["status"] == "active", summary  # provider failure != unavailable
    assert summary["provider_failures"] == 1, summary


def test_refresh_marks_sold_when_provider_confirms(clean):
    from app.workers.refresh import run_property_refresh

    prop = _record()
    _store(clean, prop)
    changed = dict(prop)
    changed["status"] = "sold"

    class ConfirmSoldProvider(FakeProvider):
        async def refresh(self, source_listing_id):
            self.refresh_calls.append(source_listing_id)
            return dict(changed)

    with patch("app.workers.refresh.get_property_provider", return_value=ConfirmSoldProvider([changed])):
        run_property_refresh(clean)

    doc = clean["properties"].find_one({"source_listing_id": "L-1"})
    assert doc["status"] == "sold"


def test_refresh_skips_listing_missing_from_provider(clean):
    """Listing absent from a healthy provider ages verification but stays active
    (only the stale worker handles the absence window)."""
    from app.workers.refresh import run_property_refresh

    prop = _record()
    _store(clean, prop)

    class EmptyProvider(FakeProvider):
        async def refresh(self, source_listing_id):
            self.refresh_calls.append(source_listing_id)
            from app.providers.property.errors import ProviderListingNotFoundError
            raise ProviderListingNotFoundError("no longer returned")

    with patch("app.workers.refresh.get_property_provider", return_value=EmptyProvider([prop])):
        summary = run_property_refresh(clean)

    doc = clean["properties"].find_one({"source_listing_id": "L-1"})
    assert doc["status"] == "active"
    assert summary["skipped"] >= 1


def test_stale_lifecycle_active_stale_expired(clean, monkeypatch):
    from app.workers.stale import run_stale_detection

    monkeypatch.setattr(settings, "LISTING_STALE_AFTER_HOURS", 1)
    monkeypatch.setattr(settings, "LISTING_EXPIRE_AFTER_DAYS", 30)

    old = dict(_record())
    created = _store(clean, old)
    clean["properties"].update_one(
        {"_id": created.id},
        {"$set": {"last_seen_at": datetime.now(timezone.utc) - timedelta(days=30)}},
    )

    run_stale_detection(clean)
    doc = clean["properties"].find_one({"_id": created.id})
    assert doc["status"] == "stale"
    assert doc["stale_at"] is not None

    # Force expiry: make stale_at in the deep past and expire window tiny.
    clean["properties"].update_one(
        {"_id": created.id},
        {"$set": {"status": "stale", "stale_at": datetime.now(timezone.utc) - timedelta(days=60)}},
    )
    monkeypatch.setattr(settings, "LISTING_EXPIRE_AFTER_DAYS", 1)
    run_stale_detection(clean)

    doc = clean["properties"].find_one({"_id": created.id})
    assert doc["status"] == "expired"
    assert doc["is_active"] is False


def test_worker_lock_is_single_flight(clean):
    from app.workers.base import acquire_lock, release_lock

    result = acquire_lock(clean, "unit_lock", ttl_seconds=30)
    assert result.acquired is True
    again = acquire_lock(clean, "unit_lock", ttl_seconds=30)
    assert again.acquired is False

    assert release_lock(clean, "unit_lock", result.owner) is True
    # Releasing with the wrong owner must not work.
    third = acquire_lock(clean, "unit_lock", ttl_seconds=30)
    assert third.acquired is True
    assert release_lock(clean, "unit_lock", "wrong-owner") is False


def test_worker_lock_recovers_after_expiry(clean):
    from app.workers.base import acquire_lock, release_lock

    first = acquire_lock(clean, "expire_lock", ttl_seconds=1)
    assert first.acquired is True
    clean["worker_locks"].update_one(
        {"_id": "expire_lock"},
        {"$set": {"locked_until": datetime.now(timezone.utc) - timedelta(seconds=5)}},
    )
    second = acquire_lock(clean, "expire_lock", ttl_seconds=30)
    assert second.acquired is True
    release_lock(clean, "expire_lock", second.owner)


def test_worker_run_tracker_records_failure(clean):
    from app.workers.base import WorkerRunTracker

    try:
        with WorkerRunTracker(clean, "unit_worker") as run:
            run.processed = 3
            run.failure = 2
            raise ValueError("boom")
    except ValueError:
        pass

    doc = clean["worker_runs"].find_one({"worker_name": "unit_worker"})
    assert doc is not None
    assert doc["status"] == "failed"
    assert "boom" in doc["error_summary"]
    assert doc["processed_count"] == 3
    assert doc["failure_count"] == 2
    assert doc.get("completed_at") is not None


def test_no_provider_means_empty_run_not_fake(clean):
    from app.workers.ingestion import run_property_ingestion
    from app.providers.property.unconfigured import UnconfiguredPropertyProvider

    with patch("app.workers.ingestion.get_property_provider", return_value=UnconfiguredPropertyProvider()):
        summary = run_property_ingestion(clean, source="test_feed", source_type="partner_api")

    # Honest behaviour: nothing is created, the run is recorded as skipped.
    assert clean["properties"].count_documents({}) == 0
    assert summary["status"] == "skipped", summary
    run_doc = clean["worker_runs"].find_one({"worker_name": "property_ingestion"})
    assert run_doc is not None
    assert "No property provider configured" in run_doc.get("error_summary", "")


def test_stale_worker_respects_thresholds_from_config(clean, monkeypatch):
    from app.workers.stale import run_stale_detection

    monkeypatch.setattr(settings, "LISTING_STALE_AFTER_HOURS", 1)
    monkeypatch.setattr(settings, "LISTING_EXPIRE_AFTER_DAYS", 7)

    recent = dict(_record())
    recent["source_listing_id"] = "L-FRESH"
    recent_created = _store(clean, recent)
    clean["properties"].update_one(
        {"_id": recent_created.id},
        {"$set": {"last_seen_at": datetime.now(timezone.utc)}},
    )

    old = dict(_record())
    old["source_listing_id"] = "L-OLD"
    old_created = _store(clean, old)
    clean["properties"].update_one(
        {"_id": old_created.id},
        {"$set": {"last_seen_at": datetime.now(timezone.utc) - timedelta(days=7)}},
    )

    run_stale_detection(clean)

    assert clean["properties"].find_one({"_id": recent_created.id})["status"] == "active"
    assert clean["properties"].find_one({"_id": old_created.id})["status"] == "stale"