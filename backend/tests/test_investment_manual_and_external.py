"""Investment analysis with manual prices and external market estimates.

Financial calculations must stay deterministic and sourced: catalogue prices
come from MongoDB, manual prices are user input, and external prices are
medians of retrieved observations. Nothing may be invented to make an analysis
work.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.finance import InvestmentRequest
from app.services.finance_service import FinanceService
from tests.fake_mongo import FakeDB


@pytest.fixture
def store() -> FakeDB:
    store = FakeDB()
    store["properties"].insert_one({
        "_id": 7001,
        "title": "Catalogue Flat",
        "slug": "catalogue-flat",
        "price": 8_000_000.0,
        "currency": "INR",
        "property_type": "apartment",
        "listing_type": "sale",
        "source": "test",
        "source_type": "admin",
        "city": "Hyderabad",
        "locality": "Gachibowli",
        "area_sqft": 1400.0,
        "is_active": True,
        "verification_status": "verified",
    })
    return store


def _base_assumptions() -> dict:
    return {
        "monthly_rent": 30_000,
        "annual_interest_rate": 8.5,
        "tenure_years": 20,
        "down_payment_pct": 20,
        "holding_years": 5,
    }


# ─── manual entry (no catalogue listing required) ──────────────────────────

def test_manual_property_is_analysed_without_catalogue_records(store: FakeDB):
    result = FinanceService(store).investment_analysis(
        [],
        manual_properties=[{
            "label": "Hyderabad 3BHK (manual)",
            "price": 12_000_000,
            "area_sqft": 1600,
            "monthly_rent": 35_000,
        }],
        **_base_assumptions(),
    )
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["price_source"] == "user_input"
    assert item["property_id"] is None
    assert item["asking_price"] == 12_000_000.0
    assert item["price_per_sqft"] == 7500.0
    # Deterministic EMI: 9.6M @ 8.5% / 20y
    assert item["loan"]["monthly_emi"] == pytest.approx(83_311.03, abs=1.0)
    assert item["loan"]["loan_amount"] == 9_600_000.0
    assert item["cash_flow"]["net_cash_flow_monthly"] < 0  # rent below EMI + costs
    assert set(item["scenarios"]) == {"conservative", "base", "optimistic"}
    assert item["yields"]["gross_rental_yield_pct"] == pytest.approx(3.5, abs=0.01)
    assert result["skipped"] == []


def test_catalogue_and_manual_properties_can_be_combined(store: FakeDB):
    result = FinanceService(store).investment_analysis(
        [7001],
        manual_properties=[{"label": "Manual entry", "price": 5_000_000}],
        monthly_rent=20_000,
    )
    sources = {item["price_source"] for item in result["items"]}
    assert sources == {"catalogue", "user_input"}
    assert result["items"][0]["property_id"] == 7001


def test_missing_catalogue_id_is_reported_not_silently_dropped(store: FakeDB):
    result = FinanceService(store).investment_analysis([424242], monthly_rent=0)
    assert result["items"] == []
    assert result["skipped"][0]["reference"] == "catalogue:424242"


# ─── external estimates ───────────────────────────────────────────────────

class _FakeResearch:
    """Deterministic external research payload (median of observations)."""

    def research(self, flt, *, use_cache=True):
        return {
            "status": "ok",
            "statistics": {
                "asking_price": {"available": True, "median": 6_650_000.0, "sample_size": 9, "is_measured": True},
                "rent_monthly": {"available": True, "median": 15_000.0, "sample_size": 4, "is_measured": True},
            },
            "resolved": {"city": "Nandyal"},
            "sources": [
                {"title": "Rates", "url": "https://example.com/rates", "domain": "example.com",
                 "published_at": None, "retrieved_at": "2026-01-01T00:00:00+00:00"},
            ],
        }


def test_external_location_uses_retrieved_median(store: FakeDB, monkeypatch):
    import app.services.external_market_service as ems

    monkeypatch.setattr(ems, "ExternalMarketService", lambda *a, **k: _FakeResearch())
    result = FinanceService(store).investment_analysis(
        [], external_locations=[{"location": "Nandyal"}], holding_years=5,
    )
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["price_source"] == "external_estimate"
    assert item["asking_price"] == 6_650_000.0
    assert "9 source(s)" in item["price_source_note"]
    assert item["external_sources"][0]["url"] == "https://example.com/rates"
    # Retrieved rent observation feeds the cash-flow model.
    assert item["yields"]["gross_rental_yield_pct"] > 0


def test_external_location_without_observations_is_skipped(store: FakeDB, monkeypatch):
    import app.services.external_market_service as ems

    class _Empty:
        def research(self, flt, *, use_cache=True):
            return {"status": "no_results", "statistics": {}}

    monkeypatch.setattr(ems, "ExternalMarketService", lambda *a, **k: _Empty())
    result = FinanceService(store).investment_analysis(
        [], external_locations=[{"location": "Nowhere"}],
    )
    assert result["items"] == []
    assert result["skipped"][0]["reference"] == "external:Nowhere"
    assert "No external asking-price observation" in result["skipped"][0]["reason"]


# ─── request validation ───────────────────────────────────────────────────

def test_request_requires_at_least_one_property():
    with pytest.raises(ValidationError):
        InvestmentRequest.model_validate({"monthly_rent": 1000})


def test_request_rejects_more_than_four_properties():
    with pytest.raises(ValidationError):
        InvestmentRequest.model_validate({
            "manual_properties": [{"label": f"P{i}", "price": 1_000_000} for i in range(5)],
        })


def test_request_accepts_manual_only():
    request = InvestmentRequest.model_validate({
        "manual_properties": [{"label": "Manual", "price": 1_000_000}],
    })
    assert request.property_ids == []


def test_request_rejects_nonsensical_assumptions():
    with pytest.raises(ValidationError):
        InvestmentRequest.model_validate({
            "manual_properties": [{"label": "M", "price": 1_000_000}],
            "annual_interest_rate": -5,
        })
    with pytest.raises(ValidationError):
        InvestmentRequest.model_validate({
            "manual_properties": [{"label": "M", "price": -1}],
        })
