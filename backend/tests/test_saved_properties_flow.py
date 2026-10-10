"""Saved-properties API behaviour: persistence, authorization, and validation.

The core regression this file guards against is a saved property not appearing
on the Saved Properties page. It asserts the full round trip — save, list,
unsave — plus the ownership boundary (one user can never read or modify
another user's saved rows).

Fixtures are deliberately not named after a live database handle: the fake
in-memory store is safe to use in CI, so these tests must run rather than be
skipped by the live-database guard in ``conftest.py``.
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

USER_A = User(id=4242, email="a@example.test", full_name="User A", hashed_password="x", role="user")
USER_B = User(id=7777, email="b@example.test", full_name="User B", hashed_password="x", role="user")


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def store() -> FakeDB:
    return FakeDB()


def _client(store: FakeDB, user: User = USER_A) -> TestClient:
    app.dependency_overrides[get_db] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _property(store: FakeDB, pid: int, *, city: str = "Hyderabad", price: float = 5_000_000.0) -> None:
    now = datetime.now(timezone.utc)
    store["properties"].insert_one({
        "_id": pid,
        "title": f"Test Property {pid}",
        "slug": f"test-property-{pid}",
        "price": price,
        "currency": "INR",
        "property_type": "apartment",
        "listing_type": "sale",
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": 1100.0,
        "price_per_sqft": round(price / 1100.0),
        "city": city,
        "locality": "HITEC City",
        "state": "Telangana",
        "source": "test",
        "source_type": "admin",
        "verification_status": "verified",
        "is_featured": False,
        "is_synthetic": False,
        "is_active": True,
        "status": "active",
        "amenities": [],
        "images": [],
        "data_quality_score": 100.0,
        "created_at": now,
        "updated_at": now,
        "last_verified_at": now,
    })


def _save(client: TestClient, pid: int) -> int:
    response = client.post("/api/v1/saved/properties", json={"property_id": pid})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_save_then_list_shows_the_property(store: FakeDB):
    """The exact reported bug: a saved property must appear in the list."""
    _property(store, 1001)
    with _client(store) as client:
        assert _save(client, 1001) > 0

        rows = client.get("/api/v1/saved/properties").json()
        assert len(rows) == 1
        assert rows[0]["property_id"] == 1001
        assert rows[0]["property"]["title"] == "Test Property 1001"
        # The UI needs currency and price-per-sqft to render a real card.
        assert rows[0]["property"]["currency"] == "INR"
        assert rows[0]["property"]["price_per_sqft"] > 0


def test_two_saved_properties_both_appear(store: FakeDB):
    _property(store, 1001)
    _property(store, 1002)
    with _client(store) as client:
        _save(client, 1001)
        _save(client, 1002)
        rows = client.get("/api/v1/saved/properties").json()
        assert sorted(r["property_id"] for r in rows) == [1001, 1002]


def test_unsaving_removes_only_that_property(store: FakeDB):
    _property(store, 1001)
    _property(store, 1002)
    with _client(store) as client:
        _save(client, 1001)
        _save(client, 1002)

        response = client.delete("/api/v1/saved/properties/1001")
        assert response.status_code == 200
        assert response.json()["property_id"] == 1001

        rows = client.get("/api/v1/saved/properties").json()
        assert [r["property_id"] for r in rows] == [1002]


def test_saving_twice_does_not_duplicate(store: FakeDB):
    _property(store, 1001)
    with _client(store) as client:
        _save(client, 1001)
        response = client.post("/api/v1/saved/properties", json={"property_id": 1001})
        assert response.status_code == 201
        assert response.json()["already_saved"] is True
        assert len(client.get("/api/v1/saved/properties").json()) == 1


def test_saved_list_filters_and_sorts(store: FakeDB):
    _property(store, 1001, city="Hyderabad", price=4_000_000.0)
    _property(store, 1002, city="Mumbai", price=9_000_000.0)
    with _client(store) as client:
        _save(client, 1001)
        _save(client, 1002)

        rows = client.get("/api/v1/saved/properties?sort_by=price&sort_order=asc").json()
        assert [r["property"]["price"] for r in rows] == [4_000_000.0, 9_000_000.0]

        assert [r["property_id"] for r in client.get("/api/v1/saved/properties?city=Hyderabad").json()] == [1001]
        assert [r["property_id"] for r in client.get("/api/v1/saved/properties?min_price=5000000").json()] == [1002]


def test_saving_unknown_property_is_rejected(store: FakeDB):
    with _client(store) as client:
        assert client.post("/api/v1/saved/properties", json={"property_id": 999999}).status_code == 404


def test_negative_property_id_is_rejected(store: FakeDB):
    with _client(store) as client:
        assert client.post("/api/v1/saved/properties", json={"property_id": -5}).status_code == 422


def test_saved_properties_require_authentication(store: FakeDB):
    _property(store, 1001)
    with _client(store) as client:
        _save(client, 1001)
    app.dependency_overrides.pop(get_current_user, None)
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/v1/saved/properties").status_code == 401


def test_one_user_cannot_read_another_users_saved_properties(store: FakeDB):
    """Ownership is enforced server-side, not by what the client claims."""
    _property(store, 1001)
    with _client(store) as client:
        _save(client, 1001)

    with _client(store, USER_B) as other:
        # User B sees none of User A's saved list ...
        assert other.get("/api/v1/saved/properties").json() == []
        assert other.get("/api/v1/saved/properties/ids").json()["property_ids"] == []
        # ... and cannot update or delete User A's saved row.
        assert other.patch("/api/v1/saved/properties/1001", json={"notes": "x"}).status_code == 404
        assert other.delete("/api/v1/saved/properties/1001").status_code == 404

    # User A's row survives untouched.
    with _client(store) as client:
        assert [r["property_id"] for r in client.get("/api/v1/saved/properties").json()] == [1001]


def test_one_user_cannot_read_another_users_comparison(store: FakeDB):
    _property(store, 1001)
    _property(store, 1002)
    with _client(store) as client:
        comparison_id = client.post(
            "/api/v1/saved/comparisons", json={"property_ids": [1001, 1002]}
        ).json()["id"]

    with _client(store, USER_B) as other:
        assert other.get(f"/api/v1/saved/comparisons/{comparison_id}").status_code == 404
        assert other.delete(f"/api/v1/saved/comparisons/{comparison_id}").status_code == 404

    with _client(store) as client:
        assert client.get(f"/api/v1/saved/comparisons/{comparison_id}").status_code == 200


def test_comparison_rejects_duplicate_and_missing_ids(store: FakeDB):
    _property(store, 1001)
    _property(store, 1002)
    with _client(store) as client:
        # Duplicates collapse to one id, which is fewer than two distinct ones.
        assert client.post(
            "/api/v1/saved/comparisons", json={"property_ids": [1001, 1001]}
        ).status_code == 422

        # A missing id is reported by name rather than silently dropped.
        response = client.post(
            "/api/v1/saved/comparisons", json={"property_ids": [1001, 999999]}
        )
        assert response.status_code == 400
        assert "999999" in response.json()["detail"]

        # Negative ids never reach the database.
        assert client.post(
            "/api/v1/saved/comparisons", json={"property_ids": [-1, -2]}
        ).status_code == 422


def test_stale_saved_record_is_skipped_not_fatal(store: FakeDB):
    _property(store, 1001)
    store["saved_properties"].insert_one({
        "_id": 1, "user_id": USER_A.id, "property_id": 424242,
        "notes": None, "created_at": datetime.now(timezone.utc),
    })
    with _client(store) as client:
        _save(client, 1001)
        rows = client.get("/api/v1/saved/properties").json()
        assert [r["property_id"] for r in rows] == [1001]
