"""RealEstateGPT - Finance API routes.

Deterministic financial calculators. The LLM only explains these numbers; it
never computes them. Estimates and fairness are derived from the actual
property catalogue stored in MongoDB.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_db
from app.core.security import get_optional_user
from app.models.user import User
from app.schemas.finance import (
    AffordabilityRequest, AffordabilityResponse,
    EmiRequest, EmiResponse,
    PriceEstimateResponse, PriceFairnessResponse,
    RentalYieldRequest, RentalYieldResponse,
    RoiRequest, RoiResponse,
)
from app.services.finance_service import FinanceService

router = APIRouter(prefix="/finance", tags=["Finance"])


@router.post("/emi", response_model=EmiResponse)
async def emi(data: EmiRequest):
    """Monthly EMI for a loan (deterministic amortization formula)."""
    return FinanceService.emi(data.principal, data.annual_interest_rate, data.tenure_years)


@router.post("/affordability", response_model=AffordabilityResponse)
async def affordability(data: AffordabilityRequest):
    """Affordable loan amount and property price from monthly income."""
    return FinanceService.affordability(
        data.monthly_income,
        data.existing_obligations,
        data.down_payment,
        data.annual_interest_rate,
        data.tenure_years,
        data.max_income_ratio,
        data.property_price,
    )


@router.post("/rental-yield", response_model=RentalYieldResponse)
async def rental_yield(data: RentalYieldRequest):
    """Gross/net rental yield for a property investment."""
    return FinanceService.rental_yield(data.property_price, data.monthly_rent, data.annual_expenses_pct)


@router.post("/roi", response_model=RoiResponse)
async def roi(data: RoiRequest):
    """Projected investment return over N years."""
    return FinanceService.roi(
        data.purchase_price, data.annual_rent, data.annual_expenses,
        data.appreciation_pct, data.years,
    )


@router.get("/properties/{property_id}/estimate", response_model=PriceEstimateResponse)
async def property_estimate(property_id: int, db=Depends(get_db)):
    """Estimated market price range for a property, from catalogue comparables."""
    try:
        return FinanceService(db).estimate(property_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")


@router.get("/properties/{property_id}/fairness", response_model=PriceFairnessResponse)
async def property_fairness(property_id: int, db=Depends(get_db)):
    """Price fairness verdict against catalogue comparables."""
    try:
        return FinanceService(db).fairness(property_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")