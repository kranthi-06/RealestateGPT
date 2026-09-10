"""RealEstateGPT - Finance schemas: EMI, affordability, yield, ROI, price analysis."""

from pydantic import BaseModel, Field
from typing import Optional, List


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
    emi_to_income_ratio: float
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