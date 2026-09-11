"""Integration tests against the configured MongoDB database.

These prove that the application's own repositories can read and write
real documents in the configured MongoDB (Atlas in production, or a local
mongod). Tests are skipped automatically when MONGODB_URI is not set.

Run from backend/:
    python -m pytest tests/test_mongo_integration.py -q
"""

import pytest

from app.core.config import settings
from app.core.database import close_connection, connect, get_database
from app.models.property import Property
from app.repositories.property_repo import PropertyRepository
from app.repositories.saved_repo import SavedRepository
from app.repositories.user_repo import UserRepository

pytestmark = pytest.mark.skipif(
    not settings.MONGODB_URI, reason="MONGODB_URI is not configured"
)


@pytest.fixture(scope="module")
def mongo():
    connect()
    db = get_database()
    yield db
    close_connection()


def test_ping(mongo):
    from app.core.database import ping

    assert ping() is True


def test_user_repository_roundtrip(mongo):
    repo = UserRepository(mongo)
    user = repo.create(
        email="itest@example.com", full_name="Integration Test", password="Passw0rd1"
    )
    try:
        found = repo.get_by_email("ITEST@example.com")
        assert found is not None
        assert found.email == "itest@example.com"
        updated = repo.update(user.id, full_name="Integration Test Two")
        assert updated is not None and updated.full_name == "Integration Test Two"
        assert repo.count() >= 1
    finally:
        mongo["users"].delete_one({"_id": user.id})


def test_property_repository_search(mongo):
    from app.core.database import next_id, point

    pid = next_id(mongo, "properties")
    prop = Property(
        id=pid,
        title="Integration Test Property 3BHK HITEC City",
        slug="integration-test-property",
        price=7500000,
        property_type="apartment",
        listing_type="sale",
        bedrooms=3,
        bathrooms=3,
        city="Hyderabad",
        locality="HITEC City",
        latitude=17.4435,
        longitude=78.3772,
        is_synthetic=True,
        source="seed_data",
        source_type="demo",
    )
    prop.location = point(prop.latitude, prop.longitude)
    doc = prop.model_dump(exclude={"id"}, exclude_none=True)
    doc["test_marker"] = "integration"
    mongo["properties"].insert_one({"_id": pid, **doc})
    try:
        repo = PropertyRepository(mongo)
        found, total = repo.search(
            city="Hyderabad", bedrooms=3, min_price=7000000, max_price=8000000
        )
        assert total >= 1
        assert any(p.id == pid for p in found)
        by_id = repo.get_by_id(pid)
        assert by_id is not None and by_id.locality == "HITEC City"
    finally:
        mongo["properties"].delete_one({"_id": pid})


def test_saved_property_is_ownership_scoped(mongo):
    from app.core.database import next_id

    repo = SavedRepository(mongo)
    user_a = next_id(mongo, "users")
    user_b = next_id(mongo, "users")
    prop_id = next_id(mongo, "properties")
    try:
        repo.save_property(user_a, prop_id, notes="for integration test")
        assert repo.is_saved(user_a, prop_id) is True
        # User B must never see User A's saved property.
        assert repo.is_saved(user_b, prop_id) is False
        ids_a = repo.get_saved_property_ids(user_a)
        assert prop_id in ids_a
        assert repo.unsave_property(user_a, prop_id) is True
        assert repo.is_saved(user_a, prop_id) is False
    finally:
        mongo["saved_properties"].delete_many({"property_id": prop_id})
        mongo["users"].delete_many({"_id": {"$in": [user_a, user_b]}})
        mongo["properties"].delete_one({"_id": prop_id})