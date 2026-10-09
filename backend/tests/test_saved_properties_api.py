"""Saved-properties API resilience tests.

A saved record whose catalogue property was deleted (or soft-deleted) used to
crash ``GET /saved/properties`` with a 500, because the stale join produced a
``None`` property that ``PropertyCardResponse`` could not validate. The endpoint
must skip stale entries and still serve the user's remaining saved properties.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from fake_mongo import FakeDB

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.user import User


def _user() -> User:
    return User(id=4242, email="saver@example.test", full_name="Saver", hashed_password="x", role="user")


def _client(db: FakeDB) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    app.dependency_overrides.clear()


def _saved_doc(saved_id: int, property_id: int) -> dict:
    return {
        "_id": saved_id,
        "user_id": 4242,
        "property_id": property_id,
        "notes": None,
        "created_at": datetime.now(timezone.utc),
    }


def test_stale_saved_record_is_skipped_not_fatal():
    """A missing/inactive property must be skipped; valid entries still return."""
    db = FakeDB()
    db["saved_properties"].insert_one(_saved_doc(1, 999))  # stale: property 999 is gone
    db["saved_properties"].insert_one(_saved_doc(2, 1001))  # stale: inactive/soft-deleted
    db["saved_properties"].insert_one(_saved_doc(3, 1002))  # valid

    db["properties"].insert_one({
        "_id": 1001, "title": "Deleted listing", "city": "Hyderabad", "is_active": False,
        "status": "active", "price": 1, "property_type": "apartment", "listing_type": "sale",
        "source": "test", "source_type": "demo",
    })
    db["properties"].insert_one({
        "_id": 1002, "title": "Live listing", "slug": "live-listing", "city": "Hyderabad",
        "is_active": True, "status": "active", "price": 1, "property_type": "apartment",
        "listing_type": "sale", "source": "test", "source_type": "demo",
    })

    with _client(db) as client:
        response = client.get("/api/v1/saved/properties")

    assert response.status_code == 200
    body = response.json()
    assert [item["property_id"] for item in body] == [1002], "stale entries are skipped, valid ones survive"


def test_all_stale_saved_records_return_empty_list():
    db = FakeDB()
    db["saved_properties"].insert_one(_saved_doc(1, 999))

    with _client(db) as client:
        response = client.get("/api/v1/saved/properties")

    assert response.status_code == 200
    assert response.json() == []


def test_saved_properties_requires_authentication():
    db = FakeDB()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/saved/properties")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 401
