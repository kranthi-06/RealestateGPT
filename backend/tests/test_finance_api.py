"""Contract tests for the deterministic finance API routes.

The calculator endpoints require no database. Estimate/fairness routes are
exercised against a stub database handle via FastAPI dependency override.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db


@pytest.fixture
def client():
    return TestClient(app)


def test_emi_contract(client):
    response = client.post("/api/v1/finance/emi", json={
        "principal": 5000000,
        "annual_interest_rate": 8.5,
        "tenure_years": 20,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["monthly_emi"] > 0
    assert body["total_repayment"] > body["principal"]
    assert body["total_interest"] > 0
    assert body["formula"] == "standard_deterministic_emi"


def test_emi_rejects_invalid_input(client):
    response = client.post("/api/v1/finance/emi", json={
        "principal": -1, "annual_interest_rate": 8.5, "tenure_years": 20,
    })
    assert response.status_code == 422


def test_affordability_contract(client):
    response = client.post("/api/v1/finance/affordability", json={
        "monthly_income": 300000,
        "existing_obligations": 50000,
        "down_payment": 2000000,
        "annual_interest_rate": 7.5,
        "tenure_years": 20,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["max_monthly_emi"] > 0
    assert body["max_loan_amount"] > 0
    assert body["max_property_price"] > body["max_loan_amount"]


def test_rental_yield_contract(client):
    response = client.post("/api/v1/finance/rental-yield", json={
        "property_price": 10000000,
        "monthly_rent": 50000,
        "annual_expenses_pct": 10,
    })
    assert response.status_code == 200
    body = response.json()
    assert abs(body["gross_yield_pct"] - 6.0) < 0.01
    assert body["net_yield_pct"] < body["gross_yield_pct"]


def test_roi_contract(client):
    response = client.post("/api/v1/finance/roi", json={
        "purchase_price": 10000000,
        "annual_rent": 600000,
        "annual_expenses": 60000,
        "appreciation_pct": 6,
        "years": 5,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["initial_yield_pct"] > 0
    assert len(body["projections"]) == 5
    assert body["projections"][-1]["year"] == 5


class _StubDb:
    """Minimal database stand-in: returns no documents for repository queries."""

    class _EmptyColl:
        def find_one(self, *_a, **_k):
            return None

        def find(self, *_a, **_k):
            return []

        def count_documents(self, *_a, **_k):
            return 0

    def __getitem__(self, _name):
        return self._EmptyColl()

    def __getattr__(self, item):
        return self._EmptyColl()


def test_estimate_missing_property_returns_typed_404(client):
    app.dependency_overrides[get_db] = lambda: _StubDb()
    try:
        response = client.get("/api/v1/finance/properties/99999999/estimate")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()