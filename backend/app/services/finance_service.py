"""RealEstateGPT - Finance service: calculators + price estimation + fairness."""

from __future__ import annotations

import logging
from statistics import median
from typing import Optional

from sqlalchemy.orm import Session

from app.finance.calculators import (
    calculate_affordability, calculate_emi, calculate_rental_yield,
    calculate_roi, price_fairness,
)
from app.ml.price_estimator import build_catalog, get_price_estimator
from app.models.property import Property
from app.repositories.property_repo import PropertyRepository

logger = logging.getLogger(__name__)


class FinanceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PropertyRepository(db)

    # ─── Deterministic calculators ─────────────────────────────────────
    @staticmethod
    def emi(principal: float, rate: float, years: float) -> dict:
        return calculate_emi(principal, rate, years)

    @staticmethod
    def affordability(monthly_income: float, existing_obligations: float = 0.0,
                      down_payment: float = 0.0, interest_rate: float = 7.5,
                      tenure_years: float = 20.0, max_ratio: float = 0.5,
                      property_price: Optional[float] = None) -> dict:
        result = calculate_affordability(
            monthly_income, existing_obligations, down_payment,
            interest_rate, tenure_years, max_ratio,
        )
        if property_price and property_price > result["max_property_price"]:
            emi_on_price = calculate_emi(
                max(0.0, property_price - down_payment), interest_rate, tenure_years
            )
            result["recommended_emi"] = emi_on_price["monthly_emi"]
            result["emi_to_income_ratio"] = round(
                emi_on_price["monthly_emi"] / monthly_income, 3
            )
            result["affordable"] = emi_on_price["monthly_emi"] <= result["max_monthly_emi"]
        return result

    @staticmethod
    def rental_yield(price: float, monthly_rent: float, expenses_pct: float = 0.0) -> dict:
        return calculate_rental_yield(price, monthly_rent, expenses_pct)

    @staticmethod
    def roi(purchase_price: float, annual_rent: float, annual_expenses: float,
            appreciation_pct: float, years: int) -> dict:
        return calculate_roi(purchase_price, annual_rent, annual_expenses,
                             appreciation_pct, years)

    # ─── Price estimation & fairness ───────────────────────────────────
    def estimate(self, property_id: int) -> dict:
        prop = self.repo.get_by_id(property_id)
        if not prop:
            raise ValueError("property_not_found")
        catalog = build_catalog(
            self.db.query(Property).filter(Property.is_active == True).all()  # noqa: E712
        )
        prop_dict = next((c for c in catalog if c["id"] == property_id), None)
        if prop_dict is None:
            raise ValueError("property_not_found")
        estimator = get_price_estimator()
        if len(catalog) >= 4:
            result = estimator.estimate(prop_dict, catalog)
        else:
            result = estimator.heuristic_estimate(prop_dict, catalog)
        result["property_id"] = property_id
        result["price_per_sqft"] = (
            prop.price_per_sqft
            or (result["estimated_price"] / prop.area_sqft if prop.area_sqft else None)
        )
        result["listed_price"] = prop.price
        result["label"] = "Estimated market range"
        return result

    def fairness(self, property_id: int) -> dict:
        prop = self.repo.get_by_id(property_id)
        if not prop:
            raise ValueError("property_not_found")
        estimate = self.estimate(property_id)
        comparables = self._comparables(prop)
        comp_median = median(comparables) if comparables else None
        comp_psf = []
        for other in self._comparables_rows(prop):
            if other.price_per_sqft:
                comp_psf.append(other.price_per_sqft)
        comp_median_psf = median(comp_psf) if comp_psf else None
        return price_fairness(
            listed_price=prop.price,
            estimated_price=estimate["estimated_price"],
            lower_bound=estimate["lower_bound"],
            upper_bound=estimate["upper_bound"],
            comparables_median=comp_median,
            listed_price_per_sqft=prop.price_per_sqft,
            comparables_price_per_sqft=comp_median_psf,
        )

    def _comparables(self, prop: Property) -> list:
        comps = self._comparables_rows(prop)
        return [c.price for c in comps]

    def _comparables_rows(self, prop: Property):
        """Fetch active sale listings in the same city within +/-35% price."""
        lo = prop.price * 0.65
        hi = prop.price * 1.35
        query = (
            self.db.query(Property)
            .filter(
                Property.id != prop.id,
                Property.is_active == True,  # noqa: E712
                Property.city == prop.city,
                Property.listing_type == "sale",
                Property.price >= lo,
                Property.price <= hi,
            )
        )
        same_type = query.filter(Property.property_type == prop.property_type).limit(8).all()
        if len(same_type) >= 3:
            return same_type
        extra = query.filter(Property.property_type != prop.property_type).limit(6 - len(same_type)).all()
        return same_type + extra