"""Search sections tests — every count must come from a real query (MongoDB)."""
from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.core.database import close_connection, connect, get_database
from app.services.search_sections_service import SearchSectionsService

pytestmark = pytest.mark.skipif(
    not settings.MONGODB_URI, reason="MONGODB_URI is not configured"
)


@pytest.fixture
def db():
    connect()
    database = get_database()
    yield database
    close_connection()


@pytest.fixture
def clean(db):
    db["properties"].delete_many({})
    yield db
    db["properties"].delete_many({})


def _dock(clean, pid, **overrides):
    base = {
        "_id": pid,
        "title": " ".join([overrides.get("locality", "HITEC City"), "Apartment"]),
        "slug": "prop-" + str(pid),
        "price": 7500000,
        "property_type": "apartment",
        "listing_type": "sale",
        "transaction_type": "sale",
        "bedrooms": 3,
        "bathrooms": 3,
        "area": 1200,
        "area_sqft": 1200,
        "city": "Hyderabad",
        "locality": "HITEC City",
        "status": "active",
        "is_active": True,
        "is_synthetic": True,
        "source": "seed_test",
        "source_type": "demo",
        "verification_status": "unverified",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    base["_id"] = pid
    clean["properties"].insert_one(base)
    return pid


def test_sections_only_include_non_empty_results(clean):
    _dock(clean, 1, bedrooms=3, price=7500000, property_type="apartment")
    _dock(clean, 2, bedrooms=2, price=5500000, property_type="apartment")

    result = SearchSectionsService(clean).build_sections({"city": "Hyderabad"})
    sections = result["sections"]

    assert any(s.id == "best_matches" and s.count == 2 for s in sections)
    bhk2 = next((s for s in sections if s.id == "bhk_2"), None)
    assert bhk2 is not None and bhk2.count == 1
    # Nobody asked for rentals -> the sections derived from the query must
    # reflect real inventory only.
    assert all(s.count > 0 for s in sections)


def test_sections_adapt_to_budget_query(clean):
    _dock(clean, 1, bedrooms=3, price=7500000)
    _dock(clean, 2, bedrooms=3, price=9000000)

    result = SearchSectionsService(clean).build_sections({"q": "3BHK under 80 lakhs in Hyderabad"})
    sections = {s.id: s for s in result["sections"]}

    assert "under_budget" in sections
    assert sections["under_budget"].count == 1


def test_rental_query_keeps_rent_section(clean):
    _dock(clean, 1, listing_type="rent", transaction_type="rent", price=25000, bedrooms=2)
    _dock(clean, 2, listing_type="sale", transaction_type="sale", price=7500000, bedrooms=2)

    result = SearchSectionsService(clean).build_sections({"q": "2BHK for rent in Hyderabad"})
    sections = {s.id: s for s in result["sections"]}

    # The intent already filters to rentals, so Best Matches ARE the rentals and
    # a redundant "For Rent" bucket is not fabricated.
    assert sections["best_matches"].count == 1
    assert sections["best_matches"].items[0].listing_type == "rent"
    # BHK buckets are skipped because the query already pinned bedrooms to 2BHK.
    assert "bhk_2" not in sections