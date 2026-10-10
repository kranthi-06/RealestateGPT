"""RealEstateGPT - Finance schemas: EMI, affordability, yield, ROI, price analysis."""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime


class EmiRequest(BaseModel):
    principal: float = Field(gt=0, description="Loan amount in INR")
    annual_interest_rate: float = Field(gt=0, le=50)
    tenure_years: float = Field(gt=0, le=40)


class EmiResponse(BaseModel):
    monthly_emi: float
    total_interest: float
    total_repayment: float
    annual_interest_rate: float
    tenure_years: float
    principal: float
    formula: str = "standard_deterministic_emi"


class AffordabilityRequest(BaseModel):
    monthly_income: float = Field(gt=0)
    existing_obligations: float = Field(0, ge=0)
    down_payment: float = Field(0, ge=0)
    property_price: Optional[float] = Field(None, gt=0)
    annual_interest_rate: float = Field(7.5, gt=0, le=50)
    tenure_years: float = Field(20, gt=0, le=40)
    max_income_ratio: float = Field(0.5, gt=0, le=1)


class AffordabilityResponse(BaseModel):
    max_monthly_emi: float
    max_loan_amount: float
    max_property_price: float
    recommended_emi: float
    """EMI as a percentage of gross monthly income (0-100), not a fraction."""
    emi_to_income_ratio: float
    max_emi_share_of_income_pct: float = 0.0
    assumptions: List[str] = []
    affordable: bool = True


class RentalYieldRequest(BaseModel):
    property_price: float = Field(gt=0)
    monthly_rent: float = Field(gt=0)
    annual_expenses_pct: float = Field(0, ge=0, le=100)


class RentalYieldResponse(BaseModel):
    gross_yield_pct: float
    net_yield_pct: float
    annual_rent: float
    annual_expenses: float
    monthly_equivalent_rent: float
    note: str = "Projection based on assumptions, not a guarantee."


class RoiRequest(BaseModel):
    purchase_price: float = Field(gt=0)
    annual_rent: float = Field(ge=0)
    annual_expenses: float = Field(0, ge=0)
    appreciation_pct: float = Field(6, ge=-50, le=100)
    years: int = Field(5, ge=1, le=30)


class YearProjection(BaseModel):
    year: int
    property_value: float
    cumulative_rent_net: float
    total_return_pct: float


class RoiResponse(BaseModel):
    initial_yield_pct: float
    annual_net_rent: float
    total_investment: float
    final_property_value: float
    total_return_pct: float
    annualized_return_pct: float
    projections: List[YearProjection]
    note: str = "Projection based on assumptions, not a guarantee."


class PriceEstimateResponse(BaseModel):
    property_id: int
    estimated_price: float
    lower_bound: float
    upper_bound: float
    price_per_sqft: Optional[float] = None
    listed_price: Optional[float] = None
    model_version: str = "heuristic"
    mae: Optional[float] = None
    rmse: Optional[float] = None
    r2: Optional[float] = None
    sample_size: int = 0
    label: str = "Estimated market range"


class PriceFairnessResponse(BaseModel):
    property_id: int
    listed_price: float
    estimated_price: float
    lower_bound: float
    upper_bound: float
    verdict: str  # below | fair | above
    verdict_label: str  # "Below estimated range" / "Fairly priced" / "Above estimated range"
    diff_pct: float
    reasons: List[str] = []
    comparables_median_price: Optional[float] = None
    listed_price_per_sqft: Optional[float] = None
    comparables_price_per_sqft: Optional[float] = None


# ─── Investment analysis ────────────────────────────────────────────────

class InvestmentRequest(BaseModel):
    """Investment model for one or more verified properties.

    ``property_ids`` may come from the client, but the property price, area and
    city are always read from the database — the request only supplies
    assumptions, never facts.
    """

    property_ids: List[int] = Field(..., min_length=1, max_length=4)
    monthly_rent: float = Field(0, ge=0)
    down_payment_pct: float = Field(20.0, gt=0, le=100)
    down_payment_amount: Optional[float] = Field(None, ge=0)
    annual_interest_rate: float = Field(8.5, gt=0, le=50)
    tenure_years: float = Field(20, gt=0, le=40)
    maintenance_monthly: float = Field(0, ge=0)
    property_tax_annual: float = Field(0, ge=0)
    insurance_annual: float = Field(0, ge=0)
    other_monthly: float = Field(0, ge=0)
    stamp_duty_pct: float = Field(5.0, ge=0, le=30)
    registration_pct: float = Field(1.0, ge=0, le=30)
    brokerage_pct: float = Field(1.0, ge=0, le=30)
    gst_pct: float = Field(0.0, ge=0, le=30)
    legal_and_misc: float = Field(25000.0, ge=0)
    loan_processing_pct: float = Field(1.0, ge=0, le=30)
    expected_vacancy_pct: float = Field(5.0, ge=0, le=100)
    rent_growth_pct: float = Field(3.0, ge=0, le=50)
    conservative_appreciation_pct: float = Field(2.0, ge=-50, le=100)
    base_appreciation_pct: float = Field(5.0, ge=-50, le=100)
    optimistic_appreciation_pct: float = Field(8.0, ge=-50, le=100)
    holding_years: int = Field(5, ge=1, le=30)


class ScenarioSummary(BaseModel):
    assumed_appreciation_pct: float
    final_property_value: float
    total_return_pct: float
    annualized_return_pct: float
    is_measured: bool = False


class LoanSummary(BaseModel):
    down_payment: float
    loan_amount: float
    ltv_pct: float
    annual_interest_rate: float
    tenure_years: float
    monthly_emi: float
    total_interest: float
    total_repayment: float


class UpfrontCosts(BaseModel):
    stamp_duty: float
    registration: float
    gst: float
    brokerage: float
    legal_and_misc: float
    loan_processing: float
    total_upfront: float
    total_cash_required: float
    assumed_rates: dict = {}


class OwnershipExpenses(BaseModel):
    maintenance_monthly: float
    sinking_fund_monthly: float
    other_monthly: float
    property_tax_annual: float
    insurance_annual: float
    monthly_total: float
    annual_total: float


class CashFlowSummary(BaseModel):
    gross_rent_monthly: float
    emi_monthly: float
    ownership_expenses_monthly: float
    net_cash_flow_monthly: float
    net_cash_flow_annual: float
    is_positive: bool


class InvestmentSummary(BaseModel):
    property_id: int
    title: str
    city: Optional[str] = None
    locality: Optional[str] = None
    area_sqft: Optional[float] = None
    asking_price: float
    price_per_sqft: Optional[float] = None
    loan: LoanSummary
    upfront_costs: UpfrontCosts
    ownership_expenses: OwnershipExpenses
    rental: dict = {}
    yields: dict = {}
    cash_flow: CashFlowSummary
    total_cash_required: float
    scenarios: dict[str, ScenarioSummary] = {}
    verified_inputs: List[str] = []
    assumption_inputs: List[str] = []
    source: Optional[str] = None
    verification_status: Optional[str] = None


class InvestmentResponse(BaseModel):
    generated_at: str
    source: str
    assumptions_note: str
    items: List[InvestmentSummary] = []
    best_net_yield: Optional[int] = None
    best_monthly_cash_flow: Optional[int] = None
    disclaimer: str = (
        "Figures use verified asking prices plus user-entered assumptions. "
        "They are not a valuation, a loan approval, or a promise of returns."
    )


# ─── Full affordability ─────────────────────────────────────────────────

class FullAffordabilityRequest(BaseModel):
    monthly_income: float = Field(..., gt=0)
    existing_obligations: float = Field(0, ge=0)
    savings: float = Field(0, ge=0)
    down_payment: float = Field(0, ge=0)
    property_price: Optional[float] = Field(None, gt=0)
    property_id: Optional[int] = Field(None, gt=0)
    monthly_rent: float = Field(0, ge=0)
    maintenance_monthly: float = Field(0, ge=0)
    property_tax_annual: float = Field(0, ge=0)
    insurance_annual: float = Field(0, ge=0)
    other_monthly: float = Field(0, ge=0)
    annual_interest_rate: float = Field(8.5, gt=0, le=50)
    tenure_years: float = Field(20, gt=0, le=40)
    max_income_ratio: float = Field(0.5, gt=0, le=1)
    stamp_duty_pct: float = Field(5.0, ge=0, le=30)
    registration_pct: float = Field(1.0, ge=0, le=30)
    brokerage_pct: float = Field(1.0, ge=0, le=30)
    gst_pct: float = Field(0.0, ge=0, le=30)
    legal_and_misc: float = Field(25000.0, ge=0)
    loan_processing_pct: float = Field(1.0, ge=0, le=30)

    @model_validator(mode="after")
    def property_reference_is_single(self) -> "FullAffordabilityRequest":
        if self.property_price is not None and self.property_id is not None:
            raise ValueError("Provide either property_price or property_id, not both")
        return self


class FullAffordabilityResponse(BaseModel):
    monthly_income: float
    existing_obligations: float
    savings: float
    net_monthly_income: float
    down_payment: float
    ownership_expenses_monthly: float
    ownership_expenses_annual: float
    surplus_monthly_at_max_emi: float
    max_monthly_emi: float
    max_loan_amount: float
    max_property_price: float
    recommended_emi: float
    emi_to_income_ratio: float
    max_emi_share_of_income_pct: float
    affordable: bool = True
    verdict: str = "comfortable"
    verdict_label: str = "Comfortable within your inputs"
    affordability_note: str = ""
    assumptions: List[str] = []
    property_assessment: Optional[dict] = None