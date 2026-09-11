"""MongoDB integration and API-contract tests for the production property domain."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import settings
from app.core.database import close_connection, connect, get_database
from app.core.security import get_current_admin, get_current_user
from app.main import app
from app.models.property import Amenity, Property
from app.models.user import User
from app.repositories.property_repo import PropertyRepository

pytestmark = pytest.mark.skipif(not settings.MONGODB_URI, reason="MONGODB_URI is not configured")


def _property(label: str, *, price: float = 7_500_000, bedrooms: int = 3, locality: str = "HITEC City") -> Property:
    token = uuid4().hex[:12]
    return Property(
        title=f"Integration {label} apartment {token}", slug=f"integration-{label.lower()}-{token}",
        price=price, currency="INR", property_type="apartment", listing_type="sale",
        bedrooms=bedrooms, bathrooms=2, area=1400, area_unit="sqft",
        furnishing="semi-furnished", city="Hyderabad", locality=locality,
        latitude=17.4435 + bedrooms / 10_000, longitude=78.3772 + bedrooms / 10_000,
        amenities=[Amenity(name="Gym"), Amenity(name="Parking")],
        source="integration_test", source_type="demo", source_id=token,
        verification_status="unverified", is_synthetic=True,
    )


@pytest.fixture(scope="module")
def repository():
    connect()
    db = get_database()
    repo = PropertyRepository(db)
    created: list[int] = []
    yield repo, created
    if created:
        # TestClient's app lifespan closes the shared client; reacquire it for
        # cleanup instead of using the fixture's now-closed database handle.
        get_database()["properties"].delete_many({"_id": {"$in": created}})
    close_connection()


def _create(repository, *properties: Property) -> list[Property]:
    repo, created = repository
    result = [repo.create_property(property_) for property_ in properties]
    created.extend(property_.id for property_ in result if property_.id is not None)
    return result


def test_property_crud_and_provenance(repository):
    repo, _ = repository
    created = _create(repository, _property("CRUD"))[0]
    assert created.id is not None and created.location["type"] == "Point"
    assert created.source_type == "demo" and created.is_synthetic is True

    fetched = repo.get_property(created.id)
    assert fetched is not None and fetched.area_sqft == 1400
    updated = repo.update_property(created.id, {"price": 7_650_000, "last_verified_at": datetime.now(timezone.utc)})
    assert updated is not None and updated.price == 7_650_000
    assert repo.delete_property(created.id) is True
    assert repo.get_property(created.id) is None


def test_filters_pagination_and_geospatial_search(repository):
    repo, _ = repository
    first, second, third = _create(
        repository,
        _property("ONE", price=6_000_000, bedrooms=2, locality="Gachibowli"),
        _property("TWO", price=8_000_000, bedrooms=3, locality="HITEC City"),
        _property("THREE", price=10_000_000, bedrooms=4, locality="HITEC City"),
    )
    price_rows, _ = repo.search_properties(min_price=7_000_000, max_price=9_000_000, page=1, page_size=20)
    assert second.id in {item.id for item in price_rows}
    assert first.id not in {item.id for item in price_rows}
    bedroom_rows, _ = repo.search_properties(bedrooms=4, page=1, page_size=20)
    assert third.id in {item.id for item in bedroom_rows}
    assert first.id not in {item.id for item in bedroom_rows}
    city_rows, _ = repo.search_properties(city="Hyderabad", locality="HITEC City", amenities=["Gym"], page=1, page_size=20)
    assert {second.id, third.id}.issubset({item.id for item in city_rows})
    paged, total = repo.list_properties(city="Hyderabad", page=1, page_size=1)
    assert len(paged) == 1 and total >= 3
    assert repo.count_properties(city="Hyderabad") >= 3
    nearby, _ = repo.geospatial_search(second.latitude, second.longitude, 2, page=1, page_size=20)
    assert second.id in {item.id for item in nearby}


def test_invalid_property_data_is_rejected():
    with pytest.raises(ValidationError):
        Property(
            title="Bad coordinates", slug="bad-coordinates", price=1, property_type="apartment",
            city="Hyderabad", latitude=17.4, source="test", source_type="demo",
        )


def test_admin_mutation_api_contract_and_authorization(repository):
    repo, created_ids = repository
    payload = {
        "title": f"API property {uuid4().hex[:10]}", "price": 5_000_000,
        "property_type": "apartment", "listing_type": "sale", "city": "Hyderabad",
        "source": "integration_test", "source_type": "demo", "source_id": uuid4().hex,
        "latitude": 17.4435, "longitude": 78.3772, "images": ["https://example.test/property.jpg"],
    }
    with TestClient(app) as client:
        unauthenticated = client.post("/api/v1/properties", json=payload)
        assert unauthenticated.status_code == 401

        regular_user = User(id=987653, email="user@example.test", full_name="User", hashed_password="x", role="user")
        app.dependency_overrides[get_current_user] = lambda: regular_user
        try:
            assert client.post("/api/v1/properties", json=payload).status_code == 403
        finally:
            app.dependency_overrides.clear()

        admin = User(id=987654, email="admin@example.test", full_name="Admin", hashed_password="x", role="admin")
        app.dependency_overrides[get_current_admin] = lambda: admin
        try:
            created = client.post("/api/v1/properties", json=payload)
            assert created.status_code == 201
            property_id = created.json()["id"]
            created_ids.append(property_id)
            listed = client.get("/api/v1/properties", params={"city": "Hyderabad", "min_price": 4_000_000, "max_price": 6_000_000, "latitude": 17.4435, "longitude": 78.3772, "radius_km": 2})
            assert listed.status_code == 200
            assert property_id in {row["id"] for row in listed.json()["properties"]}
            updated = client.patch(f"/api/v1/properties/{property_id}", json={"bedrooms": 3})
            assert updated.status_code == 200 and updated.json()["bedrooms"] == 3
            deleted = client.delete(f"/api/v1/properties/{property_id}")
            assert deleted.status_code == 204
        finally:
            app.dependency_overrides.clear()
