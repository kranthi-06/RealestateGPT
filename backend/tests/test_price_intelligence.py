"""Price intelligence tests (MongoDB; skipped without MONGODB_URI)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.database import close_connection, connect, get_database
from app.services.price_intelligence_service import PriceIntelligenceService

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
    db["price_history"].delete_many({})
    yield db
    db["properties"].delete_many({})
    db["price_history"].delete_many({})


def _dock(clean, property_id: int, price: float, area=1200.0):
    clean["properties"].insert_one({
        "_id": property_id,
        "title": "3BHK Test Property",
        "slug": "3bhk-test-property",
        "price": price,
        "property_type": "apartment",
        "listing_type": "sale",
        "city": "Hyderabad",
        "area": area,
        "area_sqft": area,
        "source": "test",
        "source_type": "admin",
        "status": "active",
        "is_active": True,
        "is_synthetic": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })


def test_price_intelligence_computes_change_from_history(clean):
    now = datetime.now(timezone.utc)
    clean["price_history"].insert_many([
        {"property_id": 1, "old_price": 7000000, "new_price": 7000000,
         "changed_at": now - timedelta(days=60), "change_type": "initial_listing"},
        {"property_id": 1, "old_price": 7000000, "new_price": 7500000,
         "changed_at": now - timedelta(days=30), "change_type": "price_increased"},
    ])
    _dock(clean, 1, 7500000, area=1500)

    result = PriceIntelligenceService(clean).get_price_intelligence(1)

    assert result["available"] is True
    assert result["current_price"] == 7500000
    assert result["previous_price"] == 7000000
    assert result["price_change_pct"] == pytest.approx(7.14, abs=0.1)
    assert result["price_per_sqft"] == pytest.approx(5000.0)
    assert result["enough_history"] is True
    assert result["observations"] == 2
    assert result["history"][0]["change_type"] == "price_increased"


def test_price_intelligence_reports_insufficient_history(clean):
    _dock(clean, 2, 5000000, area=1000)
    clean["price_history"].insert_one({
        "property_id": 2, "old_price": 5000000, "new_price": 5000000,
        "changed_at": datetime.now(timezone.utc), "change_type": "initial_listing",
    })

    result = PriceIntelligenceService(clean).get_price_intelligence(2)

    assert result["enough_history"] is False
    assert result["message"] == "Not enough verified history."
    assert result["previous_price"] is None
    assert result["price_change_pct"] is None


def test_price_intelligence_for_missing_property(clean):
    result = PriceIntelligenceService(clean).get_price_intelligence(999999)
    assert result["available"] is False


def test_price_intelligence_rent_per_sqft(clean):
    clean["properties"].insert_one({
        "_id": 3,
        "title": "2BHK Rental",
        "slug": "2bhk-rental",
        "price": 30000,
        "rent_amount": 30000,
        "rent_period": "monthly",
        "property_type": "apartment",
        "listing_type": "rent",
        "transaction_type": "rent",
        "city": "Pune",
        "area": 800,
        "area_sqft": 800,
        "source": "test",
        "source_type": "admin",
        "status": "active",
        "is_active": True,
        "is_synthetic": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    result = PriceIntelligenceService(clean).get_price_intelligence(3)
    assert result["rent_amount"] == 30000
    assert result["rent_period"] == "monthly"
    assert result["rent_per_sqft"] == pytest.approx(37.5)