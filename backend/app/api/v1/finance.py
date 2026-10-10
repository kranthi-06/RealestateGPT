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
    FullAffordabilityRequest, FullAffordabilityResponse,
    InvestmentRequest, InvestmentResponse,
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


@router.post("/affordability/full", response_model=FullAffordabilityResponse)
async def full_affordability(data: FullAffordabilityRequest, db=Depends(get_db)):
    """Affordability including savings, upfront transaction costs and ownership
    expenses, with the remaining income and savings after purchase.

    Prices are never trusted from the request body: ``property_id`` (when given)
    is resolved against the catalogue so the calculation uses the real asking
    price.
    """
    inputs = data.model_dump()
    if inputs.get("property_id") and not inputs.get("property_price"):
        from app.repositories.property_repo import PropertyRepository

        prop = PropertyRepository(db).get_by_id(inputs["property_id"])
        if prop is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
        inputs["property_price"] = prop.price
        inputs["property_id"] = None
    result = FinanceService.full_affordability(**{k: v for k, v in inputs.items() if k != "property_id"})
    return FullAffordabilityResponse(**result)


@router.post("/investment", response_model=InvestmentResponse)
async def investment_analysis(data: InvestmentRequest, db=Depends(get_db)):
    """Investment analysis for catalogue, manual, and external-market properties.

    Every figure is either a verified catalogue value, an explicit user
    assumption, or a retrieved external observation — the response keeps the
    three separate and reports skipped entries with reasons.
    """
    assumptions = data.model_dump()
    assumptions.pop("property_ids", None)
    assumptions.pop("manual_properties", None)
    assumptions.pop("external_locations", None)
    return FinanceService(db).investment_analysis(
        data.property_ids,
        manual_properties=[entry.model_dump() for entry in data.manual_properties],
        external_locations=[entry.model_dump() for entry in data.external_locations],
        **assumptions,
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