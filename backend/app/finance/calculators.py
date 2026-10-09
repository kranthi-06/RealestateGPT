"""Deterministic finance calculations; these are never delegated to an LLM."""
from __future__ import annotations


def calculate_emi(principal: float, annual_interest_rate: float, tenure_years: float) -> dict:
    months = int(round(tenure_years * 12))
    monthly_rate = annual_interest_rate / 1200
    emi = principal / months if monthly_rate == 0 else principal * monthly_rate * (1 + monthly_rate) ** months / ((1 + monthly_rate) ** months - 1)
    total = emi * months
    return {"monthly_emi": round(emi, 2), "total_interest": round(total - principal, 2),
            "total_repayment": round(total, 2), "annual_interest_rate": annual_interest_rate,
            "tenure_years": tenure_years, "principal": principal, "formula": "standard_deterministic_emi"}


def calculate_affordability(monthly_income: float, existing_obligations: float = 0.0,
                            down_payment: float = 0.0, annual_interest_rate: float = 7.5,
                            tenure_years: float = 20.0, max_income_ratio: float = 0.5) -> dict:
    """Affordability from net income, obligations and a maximum EMI share.

    ``emi_to_income_ratio`` is returned as a PERCENTAGE (0-100), not a
    fraction, so that the API, the UI and the assistant never mix units.
    """
    net_income = max(0.0, monthly_income - existing_obligations)
    max_emi = net_income * max_income_ratio
    months, rate = int(round(tenure_years * 12)), annual_interest_rate / 1200
    if rate == 0:
        loan = max_emi * months
    else:
        loan = max_emi * ((1 + rate) ** months - 1) / (rate * (1 + rate) ** months)
    emi_share_pct = round((max_emi / monthly_income * 100) if monthly_income > 0 else 0.0, 2)
    return {"max_monthly_emi": round(max_emi, 2), "max_loan_amount": round(loan, 2),
            "max_property_price": round(loan + down_payment, 2), "recommended_emi": round(max_emi, 2),
            "emi_to_income_ratio": emi_share_pct,
            "max_emi_share_of_income_pct": emi_share_pct,
            "affordable": loan > 0,
            "assumptions": [
                f"Monthly income of ₹{monthly_income:,.0f} less existing obligations of ₹{existing_obligations:,.0f} gives ₹{net_income:,.0f} of net monthly income.",
                f"Maximum EMI is capped at {round(max_income_ratio * 100)}% of net monthly income (₹{max_emi:,.0f}).",
                f"Interest rate {annual_interest_rate}% p.a. on a reducing balance (illustrative).",
                f"Tenure of {int(tenure_years)} years ({months} monthly instalments).",
                "No processing fee, insurance, stamp duty or registration cost is included.",
                "This is an estimate, not a loan offer; lender eligibility can differ.",
            ]}


def calculate_rental_yield(property_price: float, monthly_rent: float, annual_expenses_pct: float = 0.0) -> dict:
    annual_rent, expenses = monthly_rent * 12, property_price * annual_expenses_pct / 100
    return {"gross_yield_pct": round(annual_rent / property_price * 100, 2),
            "net_yield_pct": round((annual_rent - expenses) / property_price * 100, 2),
            "annual_rent": round(annual_rent, 2), "annual_expenses": round(expenses, 2),
            "monthly_equivalent_rent": round(monthly_rent, 2), "note": "Projection based on assumptions, not a guarantee."}


def calculate_roi(purchase_price: float, annual_rent: float = 0.0, annual_expenses: float = 0.0,
                  appreciation_pct: float = 6.0, years: int = 5) -> dict:
    net_rent, value, cumulative = max(0.0, annual_rent - annual_expenses), purchase_price, 0.0
    projections = []
    for year in range(1, years + 1):
        value *= 1 + appreciation_pct / 100
        cumulative += net_rent
        projections.append({"year": year, "property_value": round(value, 2), "cumulative_rent_net": round(cumulative, 2), "total_return_pct": round((value + cumulative - purchase_price) / purchase_price * 100, 2)})
    total_pct = (value + cumulative - purchase_price) / purchase_price * 100
    return {"initial_yield_pct": round(net_rent / purchase_price * 100, 2), "annual_net_rent": round(net_rent, 2),
            "total_investment": round(purchase_price, 2), "final_property_value": round(value, 2),
            "total_return_pct": round(total_pct, 2), "annualized_return_pct": round(((value + cumulative) / purchase_price) ** (1 / years) * 100 - 100, 2),
            "projections": projections, "note": "Projection based on assumptions, not a guarantee."}


def price_fairness(listed_price: float, estimated_price: float, lower_bound: float, upper_bound: float,
                   comparables_median: float | None = None, listed_price_per_sqft: float | None = None,
                   comparables_price_per_sqft: float | None = None) -> dict:
    verdict = "fair" if lower_bound <= listed_price <= upper_bound else ("below" if listed_price < lower_bound else "above")
    labels = {"fair": "Fairly priced", "below": "Below estimated range", "above": "Above estimated range"}
    reasons = [f"Listed at ₹{listed_price:,.0f} vs estimated range ₹{lower_bound:,.0f}–₹{upper_bound:,.0f}"]
    if comparables_median:
        reasons.append(f"{(listed_price - comparables_median) / comparables_median:+.0%} vs comparable-listing median")
    if verdict == "above": reasons.append("Consider negotiating or verifying whether the premium is justified.")
    if verdict == "below": reasons.append("Potential value; verify documents and listing freshness before acting.")
    return {"listed_price": listed_price, "estimated_price": estimated_price, "lower_bound": lower_bound, "upper_bound": upper_bound,
            "verdict": verdict, "verdict_label": labels[verdict], "diff_pct": round((listed_price - estimated_price) / estimated_price * 100, 2),
            "reasons": reasons, "comparables_median_price": comparables_median, "listed_price_per_sqft": listed_price_per_sqft,
            "comparables_price_per_sqft": comparables_price_per_sqft}
