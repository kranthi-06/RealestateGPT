"""RealEstateGPT - Finance service: calculators + price estimation + fairness.

All finance numbers are deterministic; the LLM only explains them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from statistics import median
from typing import Optional

from app.finance.calculators import (
    calculate_affordability, calculate_emi, calculate_full_affordability,
    calculate_investment_analysis, calculate_rental_yield, calculate_roi,
    price_fairness,
)
from app.ml.price_estimator import build_catalog, get_price_estimator
from app.models.property import Property
from app.repositories.property_repo import PropertyRepository

logger = logging.getLogger(__name__)


def _best(items: list[dict], key) -> Optional[int]:
    values = [(item["property_id"], key(item)) for item in items]
    if not values:
        return None
    best_id, best_value = values[0]
    for pid, value in values[1:]:
        if value is not None and (best_value is None or value > best_value):
            best_id, best_value = pid, value
    return best_id


class FinanceService:
    def __init__(self, db) -> None:
        self.db = db
        self.repo = PropertyRepository(db)

    # ─── Deterministic calculators ─────────────────────────────────────

    @staticmethod
    def emi(principal: float, rate: float, years: float) -> dict:
        return calculate_emi(principal, rate, years)

    @staticmethod
    def affordability(
        monthly_income: float,
        existing_obligations: float = 0.0,
        down_payment: float = 0.0,
        interest_rate: float = 7.5,
        tenure_years: float = 20.0,
        max_ratio: float = 0.5,
        property_price: Optional[float] = None,
    ) -> dict:
        result = calculate_affordability(
            monthly_income, existing_obligations, down_payment,
            interest_rate, tenure_years, max_ratio,
        )
        if property_price and property_price > result["max_property_price"]:
            emi_on_price = calculate_emi(
                max(0.0, property_price - down_payment), interest_rate, tenure_years
            )
            result["recommended_emi"] = emi_on_price["monthly_emi"]
            # Percentage of gross monthly income consumed by the target property.
            emi_share_pct = (
                round(emi_on_price["monthly_emi"] / monthly_income * 100, 2)
                if monthly_income > 0 else 0.0
            )
            result["emi_to_income_ratio"] = emi_share_pct
            result["max_emi_share_of_income_pct"] = emi_share_pct
            result["affordable"] = emi_on_price["monthly_emi"] <= result["max_monthly_emi"]
        return result

    @staticmethod
    def rental_yield(price: float, monthly_rent: float, expenses_pct: float = 0.0) -> dict:
        return calculate_rental_yield(price, monthly_rent, expenses_pct)

    # ─── Investment analysis ─────────────────────────────────────────────

    def investment_analysis(
        self,
        property_ids: Optional[list[int]] = None,
        *,
        manual_properties: Optional[list[dict]] = None,
        external_locations: Optional[list[dict]] = None,
        **assumptions,
    ) -> dict:
        """Investment model over up to four properties.

        Each entry is one of:

        * catalogue id        -> price/area/city read from MongoDB (verified)
        * manual property     -> price entered by the user (assumption)
        * external location   -> median of retrieved external observations

        Every figure in the response records where it came from
        (``price_source`` / ``verified_inputs`` / ``assumption_inputs``), and
        entries that cannot be analysed are reported in ``skipped`` with a
        reason — never silently dropped or invented.
        """
        repo = PropertyRepository(self.db)
        property_ids = list(property_ids or [])
        manual_properties = list(manual_properties or [])
        external_locations = list(external_locations or [])
        if len(property_ids) + len(manual_properties) + len(external_locations) > 4:
            raise ValueError("At most four properties can be analysed at once.")

        props = {p.id: p for p in repo.get_by_ids(property_ids)}
        fixed_down_payment = assumptions.pop("down_payment_amount", None)
        down_pct = assumptions.get("down_payment_pct", 20.0)
        items: list[dict] = []
        skipped: list[dict] = []

        for pid in property_ids:
            prop = props.get(pid)
            if prop is None:
                logger.info("investment_skipped_missing property_id=%s", pid)
                skipped.append({
                    "reference": f"catalogue:{pid}",
                    "reason": "Property is not in the catalogue.",
                })
                continue
            down_payment = (
                fixed_down_payment if fixed_down_payment is not None else prop.price * down_pct / 100
            )
            analysis = calculate_investment_analysis(
                price=prop.price,
                down_payment=down_payment,
                annual_interest_rate=assumptions.get("annual_interest_rate", 8.5),
                tenure_years=assumptions.get("tenure_years", 20.0),
                monthly_rent=assumptions.get("monthly_rent", 0.0),
                maintenance_monthly=prop.maintenance or assumptions.get("maintenance_monthly", 0.0),
                property_tax_annual=assumptions.get("property_tax_annual", 0.0),
                insurance_annual=assumptions.get("insurance_annual", 0.0),
                other_monthly=assumptions.get("other_monthly", 0.0),
                stamp_duty_pct=assumptions.get("stamp_duty_pct", 5.0),
                registration_pct=assumptions.get("registration_pct", 1.0),
                brokerage_pct=assumptions.get("brokerage_pct", 1.0),
                gst_pct=assumptions.get("gst_pct", 0.0),
                legal_and_misc=assumptions.get("legal_and_misc", 25000.0),
                loan_processing_pct=assumptions.get("loan_processing_pct", 1.0),
                expected_vacancy_pct=assumptions.get("expected_vacancy_pct", 5.0),
                rent_growth_pct=assumptions.get("rent_growth_pct", 3.0),
                appreciation_scenarios={
                    "conservative": assumptions.get("conservative_appreciation_pct", 2.0),
                    "base": assumptions.get("base_appreciation_pct", 5.0),
                    "optimistic": assumptions.get("optimistic_appreciation_pct", 8.0),
                },
                holding_years=assumptions.get("holding_years", 5),
            )
            items.append({
                "property_id": prop.id,
                "title": prop.title,
                "city": prop.city,
                "locality": prop.locality,
                "area_sqft": prop.area_sqft,
                "asking_price": round(prop.price, 2),
                "price_per_sqft": prop.price_per_sqft,
                "price_source": "catalogue",
                "price_source_note": "Asking price from the verified RealEstateGPT catalogue.",
                "external_sources": [],
                "source": prop.source,
                "verification_status": prop.verification_status,
                **analysis,
            })

        for entry in manual_properties:
            down_payment = (
                fixed_down_payment if fixed_down_payment is not None else entry["price"] * down_pct / 100
            )
            rent = entry.get("monthly_rent")
            rent = rent if rent is not None else assumptions.get("monthly_rent", 0.0)
            area = entry.get("area_sqft")
            analysis = calculate_investment_analysis(
                price=entry["price"],
                down_payment=down_payment,
                annual_interest_rate=assumptions.get("annual_interest_rate", 8.5),
                tenure_years=assumptions.get("tenure_years", 20.0),
                monthly_rent=rent,
                maintenance_monthly=assumptions.get("maintenance_monthly", 0.0),
                property_tax_annual=assumptions.get("property_tax_annual", 0.0),
                insurance_annual=assumptions.get("insurance_annual", 0.0),
                other_monthly=assumptions.get("other_monthly", 0.0),
                stamp_duty_pct=assumptions.get("stamp_duty_pct", 5.0),
                registration_pct=assumptions.get("registration_pct", 1.0),
                brokerage_pct=assumptions.get("brokerage_pct", 1.0),
                gst_pct=assumptions.get("gst_pct", 0.0),
                legal_and_misc=assumptions.get("legal_and_misc", 25000.0),
                loan_processing_pct=assumptions.get("loan_processing_pct", 1.0),
                expected_vacancy_pct=assumptions.get("expected_vacancy_pct", 5.0),
                rent_growth_pct=assumptions.get("rent_growth_pct", 3.0),
                appreciation_scenarios={
                    "conservative": assumptions.get("conservative_appreciation_pct", 2.0),
                    "base": assumptions.get("base_appreciation_pct", 5.0),
                    "optimistic": assumptions.get("optimistic_appreciation_pct", 8.0),
                },
                holding_years=assumptions.get("holding_years", 5),
            )
            items.append({
                "property_id": None,
                "title": entry["label"],
                "city": entry.get("city"),
                "locality": entry.get("locality"),
                "area_sqft": area,
                "asking_price": round(entry["price"], 2),
                "price_per_sqft": round(entry["price"] / area, 2) if area else None,
                "price_source": "user_input",
                "price_source_note": "Price entered by you; not a verified listing.",
                "external_sources": [],
                "source": "user_input",
                "verification_status": "user_entered",
                **analysis,
            })

        for entry in external_locations:
            resolved = self._external_price(entry)
            if resolved is None:
                skipped.append({
                    "reference": f"external:{entry.get('location')}",
                    "reason": (
                        "No external asking-price observation is available for this "
                        "location, so no analysis price could be used."
                    ),
                })
                continue
            price = resolved["price"]
            down_payment = (
                fixed_down_payment if fixed_down_payment is not None else price * down_pct / 100
            )
            area = entry.get("area_sqft") or resolved.get("area_sqft")
            rent = resolved.get("rent_monthly")
            rent = rent if rent is not None else assumptions.get("monthly_rent", 0.0)
            analysis = calculate_investment_analysis(
                price=price,
                down_payment=down_payment,
                annual_interest_rate=assumptions.get("annual_interest_rate", 8.5),
                tenure_years=assumptions.get("tenure_years", 20.0),
                monthly_rent=rent,
                maintenance_monthly=assumptions.get("maintenance_monthly", 0.0),
                property_tax_annual=assumptions.get("property_tax_annual", 0.0),
                insurance_annual=assumptions.get("insurance_annual", 0.0),
                other_monthly=assumptions.get("other_monthly", 0.0),
                stamp_duty_pct=assumptions.get("stamp_duty_pct", 5.0),
                registration_pct=assumptions.get("registration_pct", 1.0),
                brokerage_pct=assumptions.get("brokerage_pct", 1.0),
                gst_pct=assumptions.get("gst_pct", 0.0),
                legal_and_misc=assumptions.get("legal_and_misc", 25000.0),
                loan_processing_pct=assumptions.get("loan_processing_pct", 1.0),
                expected_vacancy_pct=assumptions.get("expected_vacancy_pct", 5.0),
                rent_growth_pct=assumptions.get("rent_growth_pct", 3.0),
                appreciation_scenarios={
                    "conservative": assumptions.get("conservative_appreciation_pct", 2.0),
                    "base": assumptions.get("base_appreciation_pct", 5.0),
                    "optimistic": assumptions.get("optimistic_appreciation_pct", 8.0),
                },
                holding_years=assumptions.get("holding_years", 5),
            )
            items.append({
                "property_id": None,
                "title": entry.get("label") or f"External market estimate — {entry['location']}",
                "city": resolved.get("city") or entry["location"],
                "locality": None,
                "area_sqft": area,
                "asking_price": round(price, 2),
                "price_per_sqft": round(price / area, 2) if area else None,
                "price_source": "external_estimate",
                "price_source_note": (
                    "Median of retrieved external asking-price observations "
                    f"({resolved.get('sample_size')} source(s)); not a verified listing."
                ),
                "external_sources": resolved.get("sources", [])[:5],
                "source": "external_web_research",
                "verification_status": "external_observation",
                **analysis,
            })

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "Mixed inputs: verified catalogue prices, user-entered prices and external observations",
            "assumptions_note": (
                "Catalogue prices and areas are verified records. Manual prices are "
                "your input. External prices are medians of retrieved web observations "
                "with their sources listed. Rent, interest rate, tenure, transaction "
                "costs, vacancy and appreciation are user-entered assumptions, not market data."
            ),
            "items": items,
            "skipped": skipped,
            "best_net_yield": _best(items, lambda i: i["yields"]["net_rental_yield_pct"]),
            "best_monthly_cash_flow": _best(items, lambda i: i["cash_flow"]["net_cash_flow_monthly"]),
        }

    def _external_price(self, entry: dict) -> Optional[dict]:
        """Resolve a price for a location from external research (cached).

        Returns ``None`` when no retrieved asking-price observation exists —
        the caller then reports the entry as skipped instead of inventing a price.
        """
        from app.services import external_market_service as external_market_module

        research = external_market_module.ExternalMarketService(self.db).research(
            external_market_module.MarketResearchFilter(
                location=entry["location"],
                listing_type=entry.get("listing_type"),
                property_type=entry.get("property_type"),
                bedrooms=entry.get("bedrooms"),
            )
        )
        stats = research.get("statistics") or {}
        asking = stats.get("asking_price") or {}
        rent = stats.get("rent_monthly") or {}
        if not asking.get("available") or not asking.get("median"):
            return None
        sources = [
            {"title": s.get("title"), "url": s.get("url"), "domain": s.get("domain"),
             "published_at": s.get("published_at"), "retrieved_at": s.get("retrieved_at")}
            for s in (research.get("sources") or [])
            if s.get("url")
        ]
        return {
            "price": asking["median"],
            "sample_size": asking.get("sample_size", 0),
            "is_measured": asking.get("is_measured", False),
            "rent_monthly": rent.get("median") if rent.get("available") else None,
            "city": (research.get("resolved") or {}).get("city") or entry["location"],
            "sources": sources,
        }

    @staticmethod
    def full_affordability(**inputs) -> dict:
        """Affordability including savings, upfront costs and recurring expenses."""
        return calculate_full_affordability(
            monthly_income=inputs["monthly_income"],
            existing_obligations=inputs.get("existing_obligations", 0.0),
            savings=inputs.get("savings", 0.0),
            down_payment=inputs.get("down_payment", 0.0),
            property_price=inputs.get("property_price"),
            monthly_rent=inputs.get("monthly_rent", 0.0),
            maintenance_monthly=inputs.get("maintenance_monthly", 0.0),
            property_tax_annual=inputs.get("property_tax_annual", 0.0),
            insurance_annual=inputs.get("insurance_annual", 0.0),
            other_monthly=inputs.get("other_monthly", 0.0),
            annual_interest_rate=inputs.get("annual_interest_rate", 8.5),
            tenure_years=inputs.get("tenure_years", 20.0),
            max_income_ratio=inputs.get("max_income_ratio", 0.5),
            stamp_duty_pct=inputs.get("stamp_duty_pct", 5.0),
            registration_pct=inputs.get("registration_pct", 1.0),
            brokerage_pct=inputs.get("brokerage_pct", 1.0),
            gst_pct=inputs.get("gst_pct", 0.0),
            legal_and_misc=inputs.get("legal_and_misc", 25000.0),
            loan_processing_pct=inputs.get("loan_processing_pct", 1.0),
        )

    @staticmethod
    def roi(
        purchase_price: float,
        annual_rent: float,
        annual_expenses: float,
        appreciation_pct: float,
        years: int,
    ) -> dict:
        return calculate_roi(
            purchase_price, annual_rent, annual_expenses, appreciation_pct, years
        )

    # ─── Price estimation & fairness ───────────────────────────────────

    def estimate(self, property_id: int) -> dict:
        prop = self.repo.get_by_id(property_id, include_inactive=True)
        if not prop:
            raise ValueError("property_not_found")
        catalog = build_catalog(self.repo.list_active())
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
        prop = self.repo.get_by_id(property_id, include_inactive=True)
        if not prop:
            raise ValueError("property_not_found")
        estimate = self.estimate(property_id)
        comparables = self._comparables(prop)
        comp_median = median(comparables) if comparables else None
        comp_psf = [other.price_per_sqft for other in self._comparables_rows(prop) if other.price_per_sqft]
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
        return [c.price for c in self._comparables_rows(prop)]

    def _comparables_rows(self, prop: Property) -> list:
        """Active sale listings in the same city within +/-35% price,
        preferring the same property type (real comparable listings only)."""
        low = prop.price * 0.65
        high = prop.price * 1.35
        same_type, _ = self.repo.search(
            city=prop.city, listing_type="sale",
            min_price=low, max_price=high,
            page=1, page_size=8, exclude_id=prop.id,
        )
        same_type = [p for p in same_type if p.property_type == prop.property_type][:8]
        if len(same_type) >= 3:
            return same_type
        others, _ = self.repo.search(
            city=prop.city, listing_type="sale",
            min_price=low, max_price=high,
            page=1, page_size=8, exclude_id=prop.id,
        )
        others = [p for p in others if p.property_type != prop.property_type][: 6 - len(same_type)]
        return same_type + others