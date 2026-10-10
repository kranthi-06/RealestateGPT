"""Tests for the finance calculators added by the investment/affordability work.

Every test asserts against an independently computed expected value, not
against whatever the implementation happens to return.
"""
from __future__ import annotations

import math

from app.finance.calculators import (
    calculate_affordability,
    calculate_emi,
    calculate_full_affordability,
    calculate_investment_analysis,
    calculate_ownership_expenses,
    calculate_purchase_costs,
    calculate_rental_yield,
    calculate_roi,
)


def _expected_emi(principal: float, annual_rate: float, years: float) -> float:
    months = int(round(years * 12))
    r = annual_rate / 1200
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


class TestEmi:
    def test_emi_matches_the_standard_formula(self):
        result = calculate_emi(4_000_000, 8.5, 20)
        assert math.isclose(result["monthly_emi"], _expected_emi(4_000_000, 8.5, 20), rel_tol=1e-6)
        assert result["total_repayment"] > result["principal"]
        assert math.isclose(
            result["total_interest"],
            result["total_repayment"] - result["principal"],
            rel_tol=1e-6,
        )

    def test_zero_interest_spreads_principal_evenly(self):
        result = calculate_emi(1_200_000, 0.0, 10)
        assert result["monthly_emi"] == 10_000.0
        assert result["total_interest"] == 0.0


class TestPurchaseCosts:
    def test_rates_are_applied_to_the_asking_price(self):
        costs = calculate_purchase_costs(
            5_000_000, stamp_duty_pct=5, registration_pct=1, brokerage_pct=1,
            loan_amount=4_000_000, loan_processing_pct=0.5, legal_and_misc=25_000,
        )
        assert costs["stamp_duty"] == 250_000
        assert costs["registration"] == 50_000
        assert costs["brokerage"] == 50_000
        assert costs["loan_processing"] == 20_000
        assert costs["legal_and_misc"] == 25_000
        assert costs["total_upfront"] == 395_000
        # Cash required = upfront + the down payment actually paid.
        assert costs["total_cash_required"] == 395_000 + 1_000_000

    def test_gst_defaults_to_zero(self):
        costs = calculate_purchase_costs(1_000_000)
        assert costs["gst"] == 0


class TestOwnershipExpenses:
    def test_monthly_and_annual_totals(self):
        expenses = calculate_ownership_expenses(
            maintenance_monthly=3000, property_tax_annual=12000,
            insurance_annual=5000, sinking_fund_monthly=500, other_monthly=250,
        )
        # monthly_total amortises the annual charges so it matches what actually
        # leaves the account each month; monthly_recurring_only is the sum of the
        # strictly monthly items.
        assert expenses["monthly_recurring_only"] == 3750
        assert expenses["monthly_total"] == 5166.67
        assert expenses["annual_total"] == 62_000.0


class TestRentalYield:
    def test_gross_and_net_yield(self):
        result = calculate_rental_yield(5_000_000, 20_000, annual_expenses_pct=1)
        assert result["annual_rent"] == 240_000
        assert result["gross_yield_pct"] == 4.8
        assert result["annual_expenses"] == 50_000
        assert result["net_yield_pct"] == 3.8


class TestRoi:
    def test_flat_appreciation_is_compounded(self):
        result = calculate_roi(1_000_000, annual_rent=60_000, appreciation_pct=5, years=2)
        assert math.isclose(result["final_property_value"], 1_000_000 * 1.05 ** 2, rel_tol=1e-6)
        assert result["total_return_pct"] > 0


class TestInvestmentAnalysis:
    def test_returns_verified_and_assumption_inputs_separately(self):
        result = calculate_investment_analysis(
            price=6_500_000, monthly_rent=25_000, down_payment=1_300_000,
            annual_interest_rate=8.5, tenure_years=20,
        )
        assert result["verified_inputs"] == ["asking_price"]
        assert "monthly_rent" in result["assumption_inputs"]
        assert "appreciation_pct" in result["assumption_inputs"]
        # Appreciation is never presented as measured market data.
        for scenario in result["scenarios"].values():
            assert scenario["is_measured"] is False

    def test_loan_and_emi_are_derived_from_price_and_down_payment(self):
        result = calculate_investment_analysis(
            price=5_000_000, down_payment=1_000_000,
            annual_interest_rate=8.5, tenure_years=20,
        )
        assert result["loan"]["loan_amount"] == 4_000_000
        assert math.isclose(
            result["loan"]["monthly_emi"], _expected_emi(4_000_000, 8.5, 20), rel_tol=1e-6
        )
        assert result["loan"]["ltv_pct"] == 80.0

    def test_cash_flow_equals_rent_minus_emi_and_ownership(self):
        result = calculate_investment_analysis(
            price=5_000_000, monthly_rent=20_000, down_payment=1_000_000,
            annual_interest_rate=8.5, tenure_years=20,
            maintenance_monthly=3000, property_tax_annual=12000,
            expected_vacancy_pct=0,
        )
        flow = result["cash_flow"]
        expected = 20_000 - flow["emi_monthly"] - flow["ownership_expenses_monthly"]
        assert math.isclose(flow["net_cash_flow_monthly"], expected, rel_tol=1e-6)
        assert math.isclose(flow["net_cash_flow_annual"], expected * 12, rel_tol=1e-6)

    def test_100_percent_down_payment_needs_no_loan(self):
        result = calculate_investment_analysis(price=4_000_000, down_payment=4_000_000)
        assert result["loan"]["loan_amount"] == 0
        assert result["loan"]["monthly_emi"] == 0

    def test_disclaimer_is_present(self):
        result = calculate_investment_analysis(price=1_000_000)
        assert "not a valuation" in result["disclaimer"]


class TestFullAffordability:
    def test_remaining_income_and_savings_after_purchase(self):
        result = calculate_full_affordability(
            monthly_income=70_000, existing_obligations=0, savings=1_200_000,
            down_payment=1_000_000, property_price=5_000_000,
            annual_interest_rate=8.5, tenure_years=20,
            maintenance_monthly=3000, property_tax_annual=12000,
        )
        assessment = result["property_assessment"]
        emi = _expected_emi(4_000_000, 8.5, 20)
        assert math.isclose(assessment["monthly_emi"], emi, rel_tol=1e-6)
        # Remaining income is gross income minus obligations minus EMI minus
        # recurring ownership costs.
        expected_remaining = 70_000 - 0 - emi - (3000 + 12000 / 12)
        assert math.isclose(assessment["remaining_income_monthly"], round(expected_remaining, 2), abs_tol=0.01)
        # Remaining savings is savings minus everything payable up front.
        upfront = assessment["upfront_costs"]["total_upfront"]
        assert math.isclose(
            assessment["cash_available_after_purchase"], 1_200_000 - (upfront + 1_000_000), rel_tol=1e-6
        )

    def test_emi_share_of_income_is_a_percentage(self):
        result = calculate_full_affordability(
            monthly_income=100_000, property_price=5_000_000, down_payment=1_000_000,
            annual_interest_rate=8.5, tenure_years=20,
        )
        ratio = result["property_assessment"]["emi_to_income_ratio_pct"]
        assert 0 < ratio < 100
        # 40,00,000 at 8.5% over 20 years is roughly â‚¹35k on â‚¹1,00,000 income.
        assert 30 < ratio < 40

    def test_affordability_is_not_decided_by_price_alone(self):
        # A low price with unaffordable cash is still not affordable.
        result = calculate_full_affordability(
            monthly_income=20_000, savings=50_000, down_payment=0,
            property_price=5_000_000, annual_interest_rate=8.5, tenure_years=20,
        )
        assert result["property_assessment"]["is_affordable"] is False
        assert result["property_assessment"]["cash_is_sufficient"] is False

    def test_legacy_affordability_still_reports_a_percentage(self):
        result = calculate_affordability(70_000, 0, 1_000_000, 8.5, 20)
        assert result["emi_to_income_ratio"] == 50.0
        assert result["max_property_price"] > result["max_loan_amount"]

    def test_verdict_reflects_burden_not_just_price(self):
        # Cheap asking price, but a maintenance burden that eats 40% of the
        # maximum EMI: the verdict must not call this "comfortable".
        heavy = calculate_full_affordability(
            monthly_income=100_000, savings=5_000_000, down_payment=1_000_000,
            property_price=5_000_000, maintenance_monthly=20_000,
        )
        assert heavy["verdict"] == "strained"
        assert heavy["verdict_label"] == "Manageable but tight"

    def test_verdict_is_not_affordable_when_ownership_exceeds_capacity(self):
        result = calculate_full_affordability(
            monthly_income=100_000, savings=5_000_000, down_payment=1_000_000,
            property_price=5_000_000, maintenance_monthly=45_000,
        )
        assert result["verdict"] == "not_affordable"

    def test_comfortable_when_costs_are_modest(self):
        comfortable = calculate_full_affordability(
            monthly_income=400_000, savings=5_000_000, down_payment=1_000_000,
            property_price=5_000_000, maintenance_monthly=3000,
        )
        assert comfortable["verdict"] == "comfortable"
        assert comfortable["property_assessment"]["is_affordable"] is True

    def test_no_loan_approval_promise(self):
        result = calculate_full_affordability(monthly_income=100_000)
        assert "not an approved loan" in result["affordability_note"]
