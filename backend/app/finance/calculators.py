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
    reasons = [f"Listed at \u20b9{listed_price:,.0f} vs estimated range \u20b9{lower_bound:,.0f}\u2013\u20b9{upper_bound:,.0f}"]
    if comparables_median:
        reasons.append(f"{(listed_price - comparables_median) / comparables_median:+.0%} vs comparable-listing median")
    if verdict == "above": reasons.append("Consider negotiating or verifying whether the premium is justified.")
    if verdict == "below": reasons.append("Potential value; verify documents and listing freshness before acting.")
    return {"listed_price": listed_price, "estimated_price": estimated_price, "lower_bound": lower_bound, "upper_bound": upper_bound,
            "verdict": verdict, "verdict_label": labels[verdict], "diff_pct": round((listed_price - estimated_price) / estimated_price * 100, 2),
            "reasons": reasons, "comparables_median_price": comparables_median, "listed_price_per_sqft": listed_price_per_sqft,
            "comparables_price_per_sqft": comparables_price_per_sqft}


# ─── Purchase cost model ────────────────────────────────────────────────

# Indicative Indian transaction-cost rates. These are DEFAULT ASSUMPTIONS,
# clearly labelled as such by every caller: the user can override each one and
# the exact rate depends on the state, the property's age and the lender.
DEFAULT_STAMP_DUTY_PCT = 5.0
DEFAULT_REGISTRATION_PCT = 1.0
DEFAULT_GST_PCT = 5.0            # under-construction only
DEFAULT_BROKERAGE_PCT = 1.0
DEFAULT_LEGAL_MISC_FLAT = 25000.0
DEFAULT_LOAN_PROCESSING_PCT = 1.0


def calculate_purchase_costs(
    property_price: float,
    *,
    stamp_duty_pct: float = DEFAULT_STAMP_DUTY_PCT,
    registration_pct: float = DEFAULT_REGISTRATION_PCT,
    gst_pct: float = 0.0,
    brokerage_pct: float = DEFAULT_BROKERAGE_PCT,
    legal_and_misc: float = DEFAULT_LEGAL_MISC_FLAT,
    loan_amount: float = 0.0,
    loan_processing_pct: float = DEFAULT_LOAN_PROCESSING_PCT,
) -> dict:
    """Upfront buying costs. Every rate is an explicit assumption, never a quote."""
    duty = property_price * stamp_duty_pct / 100
    registration = property_price * registration_pct / 100
    gst = property_price * gst_pct / 100
    brokerage = property_price * brokerage_pct / 100
    processing = loan_amount * loan_processing_pct / 100
    total = duty + registration + gst + brokerage + legal_and_misc + processing
    return {
        "stamp_duty": round(duty, 2),
        "registration": round(registration, 2),
        "gst": round(gst, 2),
        "brokerage": round(brokerage, 2),
        "legal_and_misc": round(legal_and_misc, 2),
        "loan_processing": round(processing, 2),
        "total_upfront": round(total, 2),
        "total_cash_required": round(total + max(0.0, property_price - loan_amount), 2),
        "assumed_rates": {
            "stamp_duty_pct": stamp_duty_pct,
            "registration_pct": registration_pct,
            "gst_pct": gst_pct,
            "brokerage_pct": brokerage_pct,
            "loan_processing_pct": loan_processing_pct,
        },
    }


# ─── Recurring ownership costs ───────────────────────────────────────────

def calculate_ownership_expenses(
    *,
    maintenance_monthly: float = 0.0,
    property_tax_annual: float = 0.0,
    insurance_annual: float = 0.0,
    sinking_fund_monthly: float = 0.0,
    other_monthly: float = 0.0,
) -> dict:
    """Recurring cost of owning a property, independent of the loan.

    ``monthly_total`` is the FULL monthly burden (annual charges amortised over
    twelve months), because that is what leaves the household account each
    month. ``monthly_recurring_only`` keeps the strictly monthly items apart.
    """
    monthly_recurring = maintenance_monthly + sinking_fund_monthly + other_monthly
    annual = monthly_recurring * 12 + property_tax_annual + insurance_annual
    monthly_total = annual / 12.0
    return {
        "maintenance_monthly": round(maintenance_monthly, 2),
        "sinking_fund_monthly": round(sinking_fund_monthly, 2),
        "other_monthly": round(other_monthly, 2),
        "property_tax_annual": round(property_tax_annual, 2),
        "insurance_annual": round(insurance_annual, 2),
        "monthly_recurring_only": round(monthly_recurring, 2),
        "monthly_total": round(monthly_total, 2),
        "annual_total": round(annual, 2),
    }


# ─── Investment analysis ─────────────────────────────────────────────────

def calculate_investment_analysis(
    *,
    price: float,
    monthly_rent: float = 0.0,
    down_payment: float = 0.0,
    annual_interest_rate: float = 8.5,
    tenure_years: float = 20.0,
    maintenance_monthly: float = 0.0,
    property_tax_annual: float = 0.0,
    insurance_annual: float = 0.0,
    other_monthly: float = 0.0,
    stamp_duty_pct: float = DEFAULT_STAMP_DUTY_PCT,
    registration_pct: float = DEFAULT_REGISTRATION_PCT,
    brokerage_pct: float = DEFAULT_BROKERAGE_PCT,
    gst_pct: float = 0.0,
    legal_and_misc: float = DEFAULT_LEGAL_MISC_FLAT,
    loan_processing_pct: float = DEFAULT_LOAN_PROCESSING_PCT,
    expected_vacancy_pct: float = 5.0,
    rent_growth_pct: float = 3.0,
    appreciation_scenarios: dict | None = None,
    holding_years: int = 5,
) -> dict:
    """Full investment model for one property.

    All inputs are either VERIFIED (the listing's own price) or EXPLICIT
    ASSUMPTIONS (everything else). The response separates the two so the UI can
    label them honestly. Appreciation is always a user assumption — never a
    prediction — and is reported across conservative / base / optimistic cases.
    """
    loan = max(0.0, price - down_payment)
    emi = calculate_emi(loan, annual_interest_rate, tenure_years) if loan > 0 else {
        "monthly_emi": 0.0, "total_interest": 0.0, "total_repayment": 0.0,
        "annual_interest_rate": annual_interest_rate, "tenure_years": tenure_years,
        "principal": 0.0, "formula": "no_loan_required",
    }
    upfront = calculate_purchase_costs(
        price, stamp_duty_pct=stamp_duty_pct, registration_pct=registration_pct,
        gst_pct=gst_pct, brokerage_pct=brokerage_pct, legal_and_misc=legal_and_misc,
        loan_amount=loan, loan_processing_pct=loan_processing_pct,
    )
    ownership = calculate_ownership_expenses(
        maintenance_monthly=maintenance_monthly, property_tax_annual=property_tax_annual,
        insurance_annual=insurance_annual, other_monthly=other_monthly,
    )
    effective_rent = monthly_rent * (1 - expected_vacancy_pct / 100)
    yield_result = calculate_rental_yield(price, monthly_rent, annual_expenses_pct=0.0)

    gross_monthly = monthly_rent
    net_monthly = effective_rent - emi["monthly_emi"] - ownership["monthly_total"]
    net_annual = net_monthly * 12

    scenarios = {}
    rates = appreciation_scenarios or {"conservative": 2.0, "base": 5.0, "optimistic": 8.0}
    for label, rate in rates.items():
        roi = calculate_roi(
            purchase_price=price + upfront["total_upfront"],
            annual_rent=effective_rent * 12 - ownership["annual_total"],
            annual_expenses=0.0,
            appreciation_pct=rate,
            years=holding_years,
        )
        scenarios[label] = {
            "assumed_appreciation_pct": rate,
            "final_property_value": roi["final_property_value"],
            "total_return_pct": roi["total_return_pct"],
            "annualized_return_pct": roi["annualized_return_pct"],
            "is_measured": False,
        }

    return {
        "asking_price": round(price, 2),
        "loan": {
            "down_payment": round(down_payment, 2),
            "loan_amount": round(loan, 2),
            "ltv_pct": round(loan / price * 100, 2) if price else 0.0,
            "annual_interest_rate": annual_interest_rate,
            "tenure_years": tenure_years,
            "monthly_emi": emi["monthly_emi"],
            "total_interest": emi["total_interest"],
            "total_repayment": emi["total_repayment"],
        },
        "upfront_costs": upfront,
        "ownership_expenses": ownership,
        "rental": {
            "asking_rent_monthly": round(monthly_rent, 2),
            "assumed_vacancy_pct": expected_vacancy_pct,
            "effective_rent_monthly": round(effective_rent, 2),
            "assumed_rent_growth_pct": rent_growth_pct,
        },
        "yields": {
            "gross_rental_yield_pct": yield_result["gross_yield_pct"],
            "net_rental_yield_pct": yield_result["net_yield_pct"],
        },
        "cash_flow": {
            "gross_rent_monthly": round(gross_monthly, 2),
            "emi_monthly": emi["monthly_emi"],
            "ownership_expenses_monthly": ownership["monthly_total"],
            "net_cash_flow_monthly": round(net_monthly, 2),
            "net_cash_flow_annual": round(net_annual, 2),
            "is_positive": net_monthly >= 0,
        },
        "total_cash_required": upfront["total_cash_required"],
        "scenarios": scenarios,
        "verified_inputs": ["asking_price"],
        "assumption_inputs": [
            "monthly_rent", "down_payment", "annual_interest_rate", "tenure_years",
            "maintenance_monthly", "property_tax_annual", "insurance_annual",
            "expected_vacancy_pct", "rent_growth_pct", "appreciation_pct",
            "stamp_duty_pct", "registration_pct", "brokerage_pct", "gst_pct",
        ],
        "disclaimer": (
            "Figures use verified asking prices plus user-entered assumptions. "
            "They are not a valuation, a loan approval, or a promise of returns."
        ),
    }


# ─── Affordability ──────────────────────────────────────────────────────

def calculate_full_affordability(
    *,
    monthly_income: float,
    existing_obligations: float = 0.0,
    savings: float = 0.0,
    down_payment: float = 0.0,
    property_price: float | None = None,
    monthly_rent: float = 0.0,
    maintenance_monthly: float = 0.0,
    property_tax_annual: float = 0.0,
    insurance_annual: float = 0.0,
    other_monthly: float = 0.0,
    annual_interest_rate: float = 8.5,
    tenure_years: float = 20.0,
    max_income_ratio: float = 0.5,
    stamp_duty_pct: float = DEFAULT_STAMP_DUTY_PCT,
    registration_pct: float = DEFAULT_REGISTRATION_PCT,
    brokerage_pct: float = DEFAULT_BROKERAGE_PCT,
    gst_pct: float = 0.0,
    legal_and_misc: float = DEFAULT_LEGAL_MISC_FLAT,
    loan_processing_pct: float = DEFAULT_LOAN_PROCESSING_PCT,
) -> dict:
    """Full affordability decision model.

    ``emi_to_income_ratio`` is a PERCENTAGE (0-100), not a fraction.
    """
    base = calculate_affordability(
        monthly_income, existing_obligations, down_payment,
        annual_interest_rate, tenure_years, max_income_ratio,
    )
    net_income = max(0.0, monthly_income - existing_obligations)
    max_emi = base["max_monthly_emi"]
    ownership = calculate_ownership_expenses(
        maintenance_monthly=maintenance_monthly, property_tax_annual=property_tax_annual,
        insurance_annual=insurance_annual, other_monthly=other_monthly,
    )
    ownership_monthly = ownership["monthly_total"]

    verdict, verdict_label = _affordability_verdict(max_emi, ownership_monthly)

    result = dict(base)
    result.update({
        "monthly_income": round(monthly_income, 2),
        "existing_obligations": round(existing_obligations, 2),
        "savings": round(savings, 2),
        "net_monthly_income": round(net_income, 2),
        "down_payment": round(down_payment, 2),
        "ownership_expenses_monthly": ownership_monthly,
        "ownership_expenses_annual": ownership["annual_total"],
        "surplus_monthly_at_max_emi": round(max_emi - ownership_monthly, 2),
        "verdict": verdict,
        "verdict_label": verdict_label,
        "affordability_note": (
            "An affordable EMI is not an approved loan: lenders weigh credit "
            "history, employment, existing debts and property title. Verify with "
            "your bank before committing."
        ),
    })

    if property_price and property_price > 0:
        loan = max(0.0, property_price - down_payment)
        emi = calculate_emi(loan, annual_interest_rate, tenure_years)
        upfront = calculate_purchase_costs(
            property_price, stamp_duty_pct=stamp_duty_pct, registration_pct=registration_pct,
            brokerage_pct=brokerage_pct, gst_pct=gst_pct, legal_and_misc=legal_and_misc,
            loan_amount=loan, loan_processing_pct=loan_processing_pct,
        )
        required_cash = upfront["total_cash_required"]
        monthly_outflow = emi["monthly_emi"] + ownership_monthly
        remaining_income = monthly_income - existing_obligations - monthly_outflow
        remaining_savings = savings - required_cash
        emi_share = round(emi["monthly_emi"] / monthly_income * 100, 2) if monthly_income > 0 else 0.0
        result["property_assessment"] = {
            "property_price": round(property_price, 2),
            "loan_required": round(loan, 2),
            "monthly_emi": emi["monthly_emi"],
            "total_interest": emi["total_interest"],
            "emi_to_income_ratio_pct": emi_share,
            "upfront_costs": upfront,
            "total_cash_required": round(required_cash, 2),
            "cash_shortfall": round(max(0.0, required_cash - savings), 2),
            "cash_available_after_purchase": round(remaining_savings, 2),
            "cash_is_sufficient": savings >= required_cash,
            "total_monthly_outflow": round(monthly_outflow, 2),
            "remaining_income_monthly": round(remaining_income, 2),
            "emi_within_capacity": emi["monthly_emi"] <= max_emi,
            "monthly_capacity_after_purchase": round(max_emi - emi["monthly_emi"], 2),
            "remaining_income_after_purchase": round(remaining_income, 2),
            "is_affordable": bool(emi["monthly_emi"] <= max_emi and savings >= required_cash),
        }
    return result


def _affordability_verdict(max_emi: float, ownership_monthly: float) -> tuple[str, str]:
    """Comfort | Strained | Not affordable — from the monthly burden, not the price."""
    if max_emi <= 0:
        return "not_affordable", "Not affordable on these inputs"
    if ownership_monthly >= max_emi:
        return "not_affordable", "Not affordable on these inputs"
    if ownership_monthly > max_emi * 0.5:
        return "not_affordable", "Not affordable on these inputs"
    if ownership_monthly > max_emi * 0.35:
        return "strained", "Manageable but tight"
    return "comfortable", "Comfortable within your inputs"
