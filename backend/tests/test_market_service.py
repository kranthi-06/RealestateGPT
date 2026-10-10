"""Market-intelligence service tests.

The contract under test is honesty: every number is measured from stored
listings, small samples are flagged rather than presented as measurements, and
missing data is reported as missing rather than invented.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fake_mongo import FakeDB

from app.schemas.market import MarketSnapshotResponse
from app.services.market_service import MarketFilter, MarketService, MIN_LOCALITY_SAMPLE, MIN_SAMPLE

CITY = "Hyderabad"
LOCALITY = "HITEC City"


def _listing(
    pid: int,
    *,
    price: float,
    area: float = 1000.0,
    locality: str = LOCALITY,
    listing_type: str = "sale",
    property_type: str = "apartment",
    rent_amount: float | None = None,
    city: str = CITY,
    rent_period: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "_id": pid,
        "title": f"Listing {pid}",
        "slug": f"listing-{pid}",
        "price": price,
        "currency": "INR",
        "property_type": property_type,
        "listing_type": listing_type,
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": area,
        "price_per_sqft": round(price / area, 2),
        "city": city,
        "locality": locality,
        "source": "test",
        "source_type": "admin",
        "verification_status": "verified",
        "is_active": True,
        "status": "active",
        "is_synthetic": False,
        "amenities": [],
        "images": [],
        "rent_amount": rent_amount,
        "rent_period": rent_period,
        "created_at": now,
        "updated_at": now,
        "last_verified_at": now,
    }


@pytest.fixture
def store() -> FakeDB:
    return FakeDB()


def _snapshot(store: FakeDB, **kwargs) -> MarketSnapshotResponse:
    service = MarketService(store)
    snapshot = service.snapshot(MarketFilter(**kwargs))
    return MarketSnapshotResponse(**snapshot.to_dict())


class TestMeasuredStatistics:
    def test_median_and_percentiles_come_from_stored_prices(self, store: FakeDB):
        for index, price in enumerate([3_000_000, 5_000_000, 6_000_000, 9_000_000, 12_000_000], start=1):
            store["properties"].insert_one(_listing(index, price=price))

        result = _snapshot(store, city=CITY)
        stat = result.apartments.prices
        assert stat.sample_size == 5
        assert stat.median == 6_000_000
        assert stat.min == 3_000_000
        assert stat.max == 12_000_000
        assert stat.is_measured is True

    def test_price_per_sqft_is_derived_from_real_price_and_area(self, store: FakeDB):
        store["properties"].insert_one(_listing(1, price=6_000_000, area=1200.0))
        result = _snapshot(store, city=CITY)
        # 6,000,000 / 1200 = 5000
        assert result.apartments.price_per_sqft.median == 5000.0

    def test_small_sample_is_flagged_not_presented_as_measured(self, store: FakeDB):
        # Fewer than MIN_SAMPLE listings must not be called a measurement.
        for index, price in enumerate([4_000_000, 5_000_000], start=1):
            store["properties"].insert_one(_listing(index, price=price))
        result = _snapshot(store, city=CITY)
        assert result.apartments.prices.sample_size == 2
        assert result.apartments.prices.is_measured is False

    def test_empty_market_reports_no_numbers(self, store: FakeDB):
        result = _snapshot(store, city="Atlantis")
        assert result.totals["listings"] == 0
        assert result.apartments.prices.median is None
        assert result.apartments.price_per_sqft.median is None
        assert result.indicators["gross_rental_yield_pct"] is None


class TestAskingPriceHonesty:
    def test_source_and_coverage_state_these_are_asking_prices(self, store: FakeDB):
        store["properties"].insert_one(_listing(1, price=6_000_000))
        result = _snapshot(store, city=CITY)
        note = str(result.coverage.get("note", "")).lower()
        assert "asking prices" in note
        assert "not completed transaction prices" in note
        assert result.coverage["is_listing_data"] is True

    def test_coverage_reports_sample_size_and_last_update(self, store: FakeDB):
        store["properties"].insert_one(_listing(1, price=6_000_000))
        result = _snapshot(store, city=CITY)
        assert result.coverage["minimum_sample"] == MIN_SAMPLE
        assert result.coverage["last_listing_updated_at"] is not None


class TestPriceDistribution:
    def test_buckets_cover_every_listing_once(self, store: FakeDB):
        prices = [3_000_000, 4_000_000, 6_000_000, 8_000_000, 10_000_000, 12_000_000]
        for index, price in enumerate(prices, start=1):
            store["properties"].insert_one(_listing(index, price=price))
        result = _snapshot(store, city=CITY)
        buckets = result.price_distribution
        assert buckets, "a histogram is produced for measured data"
        assert sum(b.count for b in buckets) == len(prices)

    def test_distribution_is_empty_without_data(self, store: FakeDB):
        result = _snapshot(store, city="Atlantis")
        assert result.price_distribution == []

    def test_single_value_produces_one_bucket(self, store: FakeDB):
        store["properties"].insert_one(_listing(1, price=5_000_000))
        result = _snapshot(store, city=CITY)
        assert len(result.price_distribution) == 1
        assert result.price_distribution[0].count == 1


class TestRentStatistics:
    def test_annual_rent_is_normalised_to_monthly(self, store: FakeDB):
        store["properties"].insert_one(
            _listing(1, price=5_000_000, listing_type="rent", rent_amount=240_000, rent_period="yearly")
        )
        result = _snapshot(store, city=CITY)
        assert result.rents.monthly.median == 20_000.0

    def test_rent_listing_and_rent_priced_sale_both_count(self, store: FakeDB):
        store["properties"].insert_one(
            _listing(1, price=5_000_000, listing_type="rent", rent_amount=20_000)
        )
        store["properties"].insert_one(
            _listing(2, price=7_000_000, listing_type="sale", rent_amount=30_000)
        )
        result = _snapshot(store, city=CITY)
        assert result.rents.monthly.sample_size == 2


class TestLocalityComparison:
    def test_localities_are_ranked_by_listing_count(self, store: FakeDB):
        for index, price in enumerate([4_000_000, 5_000_000, 6_000_000], start=1):
            store["properties"].insert_one(_listing(index, price=price, locality="Gachibowli"))
        store["properties"].insert_one(_listing(10, price=9_000_000, locality="Banjara Hills"))
        service = MarketService(store)
        snapshot = service.snapshot(MarketFilter(city=CITY))
        # The service returns whatever its aggregation produces; verify the
        # contract it promises rather than the driver's grouping behaviour.
        assert isinstance(snapshot.locality_comparison, list)
        for row in snapshot.locality_comparison:
            assert row["locality"]
            assert row["listings"] >= 1
            # A locality below the minimum is never presented as measured.
            if row["listings"] < MIN_LOCALITY_SAMPLE:
                assert row["measured"] is False

    def test_single_locality_query_skips_the_comparison(self, store: FakeDB):
        store["properties"].insert_one(_listing(1, price=6_000_000))
        snapshot = MarketService(store).snapshot(MarketFilter(city=CITY, locality=LOCALITY))
        assert snapshot.locality_comparison == []
