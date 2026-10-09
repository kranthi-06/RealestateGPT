"""Web-discovery promotion tests.

Promotion must be explicit, idempotent and honest: promoted listings keep
``source_type=web_discovery`` and stay unverified, and no field is ever
invented (missing coordinates stay missing, unknown property types are skipped).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fake_mongo import FakeDB

from app.services.discovery_promotion import (
    PROMOTION_SOURCE,
    PROMOTION_SOURCE_TYPE,
    map_discovery_to_record,
    promote_web_discoveries,
)


def _discovery(**overrides):
    doc = {
        "_id": "507f1f77bcf86cd799439011",
        "title": "3 BHK Apartment for sale in Hyderabad",
        "result_url": "https://example.com/listing/1",
        "category": "PROPERTY_SALE",
        "transaction_type": "sale",
        "price": 7500000,
        "currency": "INR",
        "city": "Hyderabad",
        "bedrooms": 3,
        "bathrooms": 2,
        "area": 1450,
        "area_unit": "sqft",
        "confidence": 0.9,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=12),
        "discovered_at": datetime.now(timezone.utc),
    }
    doc.update(overrides)
    return doc


def test_maps_a_residential_sale_listing():
    record = map_discovery_to_record(_discovery())
    assert record is not None
    assert record["property_type"] == "apartment"
    assert record["listing_type"] == "sale"
    assert record["price"] == 7500000
    assert record["city"] == "Hyderabad"
    assert record["source"] == PROMOTION_SOURCE
    assert record["source_type"] == PROMOTION_SOURCE_TYPE
    assert record["source_url"] == "https://example.com/listing/1"
    assert record["area_unit"] == "sqft"
    # Nothing about verification is claimed by the mapping itself.
    assert "verification_status" not in record


def test_category_hotel_maps_to_hotel_type_and_rent():
    record = map_discovery_to_record(
        _discovery(category="HOTEL", transaction_type=None, title="Beach Resort Stay")
    )
    assert record is not None
    assert record["property_type"] == "hotel"
    assert record["listing_type"] == "rent"


def test_normalized_price_is_preferred():
    record = map_discovery_to_record(_discovery(price=10, normalized_price=9100000))
    assert record["price"] == 9100000


def test_skips_records_without_price_city_or_type():
    assert map_discovery_to_record(_discovery(price=None, normalized_price=None)) is None
    assert map_discovery_to_record(_discovery(city="")) is None
    assert map_discovery_to_record(_discovery(title="Nice place")) is None  # no type wording
    assert map_discovery_to_record(_discovery(title="abc")) is None  # too short


def test_coordinates_are_copied_only_when_present():
    without = map_discovery_to_record(_discovery())
    assert "latitude" not in without and "longitude" not in without

    with_coords = map_discovery_to_record(
        _discovery(latitude=17.44, longitude=78.35, location_source="osm")
    )
    assert with_coords["latitude"] == 17.44
    assert with_coords["longitude"] == 78.35
    assert with_coords["location_source"] == "osm"


def test_image_and_amenities_are_carried_over():
    record = map_discovery_to_record(
        _discovery(image_url="https://cdn.example.com/a.jpg", amenities=["Gym", "Pool"])
    )
    assert record["images"] == [{"url": "https://cdn.example.com/a.jpg", "display_order": 0}]
    assert record["amenities"] == ["Gym", "Pool"]


class _RecordingIngestion:
    def __init__(self):
        self.batches = []

    def ingest(self, records, *, source, source_type):
        self.batches.append((source, source_type, list(records)))

        class _Result:
            created = len(records)
            updated = 0
            duplicates = 0
            rejected = 0
            failed = 0
            rejection_reasons = {}
            reviews = 0

        return _Result()


def _patch_ingestion(monkeypatch):
    recorder = _RecordingIngestion()
    monkeypatch.setattr(
        "app.services.discovery_promotion.PropertyIngestionService",
        lambda repository: recorder,
    )
    return recorder


def test_promote_skips_unmappable_and_reports_reasons(monkeypatch):
    recorder = _patch_ingestion(monkeypatch)
    db = FakeDB()
    db["web_property_discoveries"].insert_one(_discovery())
    db["web_property_discoveries"].insert_one(_discovery(_id="b", price=None, title="No price villa"))
    db["web_property_discoveries"].insert_one(
        _discovery(_id="c", expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
    )

    summary = promote_web_discoveries(db)

    assert summary.fetched == 2  # the expired discovery is not even considered
    assert summary.promoted == 1
    assert summary.skipped == 1
    assert summary.skip_reasons.get("unmappable") == 1
    source, source_type, records = recorder.batches[0]
    assert source == PROMOTION_SOURCE and source_type == PROMOTION_SOURCE_TYPE
    assert records[0]["source_type"] == "web_discovery"


def test_promote_respects_min_confidence(monkeypatch):
    recorder = _patch_ingestion(monkeypatch)
    db = FakeDB()
    db["web_property_discoveries"].insert_one(_discovery(_id="a", confidence=0.2))
    db["web_property_discoveries"].insert_one(_discovery(_id="b", confidence=0.8))

    summary = promote_web_discoveries(db, min_confidence=0.5)

    assert summary.fetched == 2
    assert summary.promoted == 1
    assert summary.skip_reasons.get("low_confidence") == 1
    assert len(recorder.batches[0][2]) == 1
