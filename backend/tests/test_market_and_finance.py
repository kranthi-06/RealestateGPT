"""Contract tests for market intelligence and finance calculations.

These tests assert the honesty contract (measured vs indicative), the
unit consistency of affordability percentages, and the numeric accuracy of
the standard amortisation EMI formula.
"""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.finance.calculators import calculate_affordability, calculate_emi
from app.main import app
from app.services.market_service import (
    MarketFilter,
    MarketService,
    _area_sqft,
    _bucket,
    _median,
    _percentile,
    _rent_monthly,
)


@pytest.fixture
def client():
    return TestClient(app)


# ─── Finance maths ──────────────────────────────────────────────────────

def _reference_emi(principal: float, annual_rate: float, years: int) -> float:
    """Independent implementation of the standard reducing-balance EMI."""
    months = years * 12
    r = annual_rate / 12 / 100
    emi = principal * r * (1 + r) ** months / ((1 + r) ** months - 1)
    total = emi * months
    return total - principal  # interest only


def test_emi_matches_standard_amortisation_formula(client):
    response = client.post("/api/v1/finance/emi", json={
        "principal": 4000000, "annual_interest_rate": 8.5, "tenure_years": 20,
    })
    assert response.status_code == 200
    body = response.json()
    expected_interest = _reference_emi(4000000, 8.5, 20)
    assert abs(body["total_interest"] - expected_interest) < 1.0
    assert math.isclose(
        body["monthly_emi"] * 240, body["total_repayment"], rel_tol=1e-6
    )
    assert abs(body["total_repayment"] - (body["principal"] + body["total_interest"])) < 1.0


def test_emi_zero_interest_is_plain_division():
    result = calculate_emi(1200000, 0.0, 10)
    assert result["monthly_emi"] == 10000.0
    assert result["total_interest"] == 0.0


def test_emi_monthly_amount_is_positive_and_bounded(client):
    response = client.post("/api/v1/finance/emi", json={
        "principal": 500000, "annual_interest_rate": 6.0, "tenure_years": 30,
    })
    assert response.status_code == 200
    emi = response.json()["monthly_emi"]
    assert 0 < emi < 500000
    # EMI must never exceed principal plus one period of interest.
    assert emi <= 500000


def test_affordability_ratio_is_a_percentage_not_a_fraction(client):
    response = client.post("/api/v1/finance/affordability", json={
        "monthly_income": 200000,
        "existing_obligations": 0,
        "down_payment": 1000000,
        "annual_interest_rate": 8.5,
        "tenure_years": 20,
    })
    assert response.status_code == 200
    body = response.json()
    # Default cap is 50% of NET monthly income; income here has no obligations,
    # so the share of GROSS income is 50%. It must read as 50.0, not 0.5.
    assert body["emi_to_income_ratio"] == 50.0
    assert body["max_emi_share_of_income_pct"] == 50.0
    assert body["max_monthly_emi"] == 100000.0
    # Loan derived from the EMI cap must be reproducible through the EMI route.
    emi_response = client.post("/api/v1/finance/emi", json={
        "principal": body["max_loan_amount"],
        "annual_interest_rate": 8.5,
        "tenure_years": 20,
    })
    assert emi_response.status_code == 200
    assert math.isclose(
        emi_response.json()["monthly_emi"], body["max_monthly_emi"], rel_tol=1e-3
    )


def test_affordability_existing_obligations_reduce_capacity():
    plain = calculate_affordability(200000, 0, 0, 8.5, 20, 0.5)
    burdened = calculate_affordability(200000, 100000, 0, 8.5, 20, 0.5)
    assert burdened["max_monthly_emi"] < plain["max_monthly_emi"]
    assert burdened["max_loan_amount"] < plain["max_loan_amount"]
    assert burdened["emi_to_income_ratio"] == 25.0  # 50% of net 1L


def test_affordability_target_price_flags_unaffordable(client):
    response = client.post("/api/v1/finance/affordability", json={
        "monthly_income": 100000,
        "existing_obligations": 0,
        "down_payment": 100000,
        "property_price": 100000000,
        "annual_interest_rate": 9.0,
        "tenure_years": 20,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["affordable"] is False
    assert body["emi_to_income_ratio"] > 50.0


def test_affordability_down_payment_increases_max_property_price():
    low = calculate_affordability(200000, 0, 100000, 8.5, 20, 0.5)
    high = calculate_affordability(200000, 0, 2000000, 8.5, 20, 0.5)
    assert high["max_property_price"] == high["max_loan_amount"] + 2000000
    assert high["max_property_price"] > low["max_property_price"]


# ─── Market service helpers ──────────────────────────────────────────────

def test_area_sqft_normalises_units():
    assert _area_sqft({"area_sqft": 1200}) == 1200.0
    assert _area_sqft({"area": 1, "area_unit": "acre"}) == 43560.0
    assert _area_sqft({"carpet_area_sqft": 900}) == 900.0
    assert _area_sqft({}) is None
    assert _area_sqft({"area_sqft": 0}) is None


def test_rent_monthly_normalises_periods():
    assert _rent_monthly({"rent_amount": 20000}) == 20000.0
    assert _rent_monthly({"rent_amount": 240000, "rent_period": "year"}) == 20000.0
    assert _rent_monthly({}) is None
    assert _rent_monthly({"rent_amount": 0}) is None


def test_property_type_buckets():
    assert _bucket("apartment") == "apartment"
    assert _bucket("Flat") == "apartment"
    assert _bucket("villa") == "house"
    assert _bucket("independent_house") == "house"
    assert _bucket("plot") == "land"
    assert _bucket("open_land") == "land"
    assert _bucket("pg") == "pg"
    assert _bucket("office") == "commercial"


def test_median_and_percentile():
    assert _median([]) is None
    assert _median([5, 1, 3]) == 3
    assert _median([4, 1, 3, 2]) == 2.5
    assert _percentile([1, 2, 3, 4], 0.25) == 1.75


# ─── Market service snapshot (DB-free via a find-only collection) ────────

class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __iter__(self):
        return iter(self._docs)


class _FindOnlyCollection:
    """Supports find() only; aggregate()/distinct() raise, exercising the
    graceful-degradation path in MarketService.

    Implements the query subset used by MarketFilter: equality, comparison
    operators, ``$or`` and ``$regex`` (so regex escaping is really tested).
    """

    def __init__(self, docs):
        self.docs = list(docs)

    def find(self, query=None, projection=None):
        return _Cursor([d for d in self.docs if _matches(d, query or {})])

    def aggregate(self, *_a, **_k):
        raise RuntimeError("aggregate not supported in this stub")

    def distinct(self, *_a, **_k):
        raise RuntimeError("distinct not supported in this stub")


class _FindOnlyDb:
    def __init__(self, docs):
        self.properties = _FindOnlyCollection(docs)
        self.price_history = _FindOnlyCollection([])

    def __getitem__(self, name):
        if name == "properties":
            return self.properties
        if name == "price_history":
            return self.price_history
        raise KeyError(name)


def _matches(doc: dict, query: dict) -> bool:
    """Subset of Mongo query matching: $or, $regex, comparison, equality."""
    for key, expected in (query or {}).items():
        if key == "$or":
            if not any(_matches(doc, clause) for clause in expected):
                return False
            continue
        if key not in doc:
            if isinstance(expected, dict) and "$exists" in expected:
                return not expected["$exists"]
            if expected is None:
                continue
            return False
        actual = doc.get(key)
        if isinstance(expected, dict):
            import re

            # Pre-scan $options: Mongo applies its flags to any $regex in the
            # same predicate regardless of key order.
            regex_flags = 0
            options = expected.get("$options")
            if isinstance(options, str) and "i" in options:
                regex_flags |= re.IGNORECASE
            for op, operand in expected.items():
                if op == "$regex":
                    if not re.search(operand, str(actual), regex_flags):
                        return False
                elif op in ("$options", "$exists"):
                    continue
                elif op == "$ne" and actual == operand:
                    return False
                elif op == "$in" and actual not in operand:
                    return False
                elif op == "$gt" and not actual > operand:
                    return False
                elif op == "$lt" and not actual < operand:
                    return False
                elif op == "$gte" and not actual >= operand:
                    return False
                elif op == "$lte" and not actual <= operand:
                    return False
                elif actual != operand:
                    return False
            continue
        if expected is not None and actual != expected:
            return False
    return True


def _listing(
    city="Nandyal",
    locality="Main Bazaar",
    listing_type="sale",
    property_type="apartment",
    price=4000000,
    area=1200,
    beds=2,
    rent=None,
    synthetic=False,
    **extra,
):
    doc = {
        "_id": id(object()),
        "city": city,
        "locality": locality,
        "listing_type": listing_type,
        "property_type": property_type,
        "price": price,
        "area_sqft": area,
        "bedrooms": beds,
        "is_active": True,
        "is_synthetic": synthetic,
    }
    if rent is not None:
        doc["rent_amount"] = rent
    doc.update(extra)
    return doc


def test_market_snapshot_computes_price_statistics_from_stored_listings():
    docs = [_listing(price=4000000 + i * 100000) for i in range(5)]
    docs += [_listing(property_type="plot", price=1200000, area=600, beds=None) for _ in range(4)]
    service = MarketService(_FindOnlyDb(docs))

    snap = service.snapshot(MarketFilter(city="Nandyal"))

    assert snap.total_listings == 9
    assert snap.apartment_prices.sample_size == 5
    assert snap.apartment_prices.median == 4200000.0
    assert snap.apartment_prices.is_measured is True
    assert snap.apartment_psf.median is not None
    # 1 sq. yard = 9 sq.ft, so land ₹/sq.yard must be 9x ₹/sq.ft.
    assert snap.land_price_per_sq_yard.median is not None
    assert snap.land_psf.median is not None
    assert math.isclose(
        snap.land_price_per_sq_yard.median, snap.land_psf.median * 9, rel_tol=1e-6
    )
    payload = snap.to_dict()
    assert payload["totals"]["verified_only"] is True
    assert payload["coverage"]["price_statistics_measured"] is True


def test_market_snapshot_flags_small_samples():
    docs = [_listing(price=4000000)]
    service = MarketService(_FindOnlyDb(docs))
    snap = service.snapshot(MarketFilter(city="Nandyal"))
    assert snap.apartment_prices.sample_size == 1
    assert snap.apartment_prices.is_measured is False
    assert snap.coverage["price_statistics_measured"] is False


def test_market_snapshot_rent_statistics_are_monthly():
    docs = [
        _listing(listing_type="rent", price=25000, area=1100, rent=25000),
        _listing(listing_type="rent", price=27000, area=1150, rent=27000),
        _listing(listing_type="rent", price=23000, area=1050, rent=23000),
    ]
    service = MarketService(_FindOnlyDb(docs))
    snap = service.snapshot(MarketFilter(city="Nandyal", listing_type="rent"))
    assert snap.rents_monthly.sample_size == 3
    assert snap.rents_monthly.median == 25000.0
    assert snap.rents_monthly.min == 23000.0
    assert snap.rents_monthly.max == 27000.0


def test_market_snapshot_year_rent_is_normalised_to_monthly():
    docs = [
        _listing(listing_type="rent", price=360000, rent=360000, rent_period="year"),
        _listing(listing_type="rent", price=480000, rent=480000, rent_period="year"),
    ]
    service = MarketService(_FindOnlyDb(docs))
    snap = service.snapshot(MarketFilter(city="Nandyal"))
    assert snap.rents_monthly.min == 30000.0
    assert snap.rents_monthly.max == 40000.0


def test_market_snapshot_empty_market_has_no_fabricated_numbers():
    service = MarketService(_FindOnlyDb([]))
    snap = service.snapshot(MarketFilter(city="Nowhere"))
    assert snap.total_listings == 0
    assert snap.apartment_prices.sample_size == 0
    assert snap.apartment_prices.median is None
    assert snap.rents_monthly.median is None
    assert snap.gross_yield_pct is None
    assert snap.price_to_rent_ratio is None
    assert snap.trend["available"] is False


# ─── Market API contract ────────────────────────────────────────────────

def test_market_insights_requires_a_location(client):
    response = client.get("/api/v1/market/insights")
    assert response.status_code == 422


def test_market_insights_returns_no_listings_reason_when_empty(client):
    app.dependency_overrides[get_db] = lambda: _FindOnlyDb([])
    try:
        response = client.get("/api/v1/market/insights?city=Nowhere")
        assert response.status_code == 200
        body = response.json()
        assert body["totals"]["listings"] == 0
        assert body["insufficient_data"] is not None
        assert body["insufficient_data"]["code"] == "NO_LISTINGS"
    finally:
        app.dependency_overrides.clear()


def test_market_insights_any_city_is_accepted(client):
    """The endpoint must not depend on a hardcoded list of cities."""
    app.dependency_overrides[get_db] = lambda: _FindOnlyDb(
        [_listing(city="Some Unknown Village", price=3500000)]
    )
    try:
        response = client.get("/api/v1/market/insights?city=Some%20Unknown%20Village")
        assert response.status_code == 200
        body = response.json()
        assert body["totals"]["listings"] == 1
        assert body["apartments"]["prices"]["sample_size"] == 1
        assert body["insufficient_data"]["code"] == "SALE_SAMPLE_TOO_SMALL"
    finally:
        app.dependency_overrides.clear()


def test_market_insights_locality_matches_case_insensitively(client):
    docs = [_listing(city="Hyderabad", locality="Banjara Hills", price=9000000) for _ in range(5)]
    app.dependency_overrides[get_db] = lambda: _FindOnlyDb(docs)
    try:
        response = client.get(
            "/api/v1/market/insights?city=Hyderabad&locality=banjara%20hills"
        )
        assert response.status_code == 200
        assert response.json()["totals"]["listings"] == 5
    finally:
        app.dependency_overrides.clear()


def test_market_insights_regex_input_is_escaped(client):
    """Regex metacharacters in user input must not break or widen the query."""
    docs = [_listing(city="Nandyal")]
    app.dependency_overrides[get_db] = lambda: _FindOnlyDb(docs)
    try:
        response = client.get("/api/v1/market/insights?city=Nand%5Cyal%28.%2A%29")
        assert response.status_code == 200
        assert response.json()["totals"]["listings"] == 0
    finally:
        app.dependency_overrides.clear()
