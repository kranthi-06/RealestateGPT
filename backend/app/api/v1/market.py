"""Market intelligence endpoints — location-based insights from stored data.

Honesty contract:
  * every figure is aggregated from verified listings in MongoDB;
  * statistics derived from a small sample are explicitly flagged
    (``is_measured``) so the UI never presents a guess as a market rate;
  * when there is not enough data the endpoint returns an explicit
    ``insufficient_data`` reason instead of inventing numbers.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import get_db
from app.core.security import get_optional_user
from app.schemas.market import (
    MarketInsightResponse,
    MarketSnapshotResponse,
)
from app.services.market_service import MarketFilter, MarketService, MIN_SAMPLE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/market", tags=["Market intelligence"])

SALE_RENT = "^$|^(sale|rent)$"


def _normalize_listing_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    if v in ("sale", "buy", "for sale"):
        return "sale"
    if v in ("rent", "rental", "lease", "for rent"):
        return "rent"
    return None


@router.get("/insights", response_model=MarketSnapshotResponse)
async def market_insights(
    city: Optional[str] = Query(None, max_length=100),
    locality: Optional[str] = Query(None, max_length=100),
    listing_type: Optional[str] = Query(None, pattern=SALE_RENT),
    property_type: Optional[str] = Query(None, max_length=50),
    bedrooms: Optional[int] = Query(None, ge=0, le=20),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    include_history: bool = Query(True),
    db=Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """Return price/rent/trend statistics for a searched city + locality.

    The search is free-text and not limited to any hardcoded city list; the
    filter is matched case-insensitively against stored ``city``/``locality``.
    """
    if not city and not locality:
        raise HTTPException(status_code=422, detail="Provide a city or locality to analyse.")

    flt = MarketFilter(
        city=city,
        locality=locality,
        listing_type=_normalize_listing_type(listing_type),
        property_type=property_type,
        bedrooms=bedrooms,
        min_price=min_price,
        max_price=max_price,
    )
    service = MarketService(db)
    snapshot = service.snapshot(flt, include_history=include_history)
    payload = snapshot.to_dict()

    if snapshot.total_listings == 0:
        payload["insufficient_data"] = {
            "code": "NO_LISTINGS",
            "reason": (
                "No verified listings are stored for this location. "
                "Market statistics are not generated when there is no inventory to measure."
            ),
        }
    elif snapshot.sale_listings < MIN_SAMPLE:
        payload["insufficient_data"] = {
            "code": "SALE_SAMPLE_TOO_SMALL",
            "reason": (
                f"Only {snapshot.sale_listings} sale listing(s) are stored for this location; "
                f"at least {MIN_SAMPLE} are needed before price statistics are treated as measured."
            ),
        }

    return MarketSnapshotResponse(**payload)


@router.get("/summary", response_model=MarketInsightResponse)
async def market_summary(
    city: Optional[str] = Query(None, max_length=100),
    db=Depends(get_db),
):
    """Compact per-city totals used by the Market Intelligence landing cards."""
    service = MarketService(db)
    rows = service.city_totals(city)
    return MarketInsightResponse(
        generated_at=snapshot_now(),
        cities=rows,
        minimum_sample=MIN_SAMPLE,
        note=(
            "Counts are verified stored listings only. "
            "No external feed, seeded price, or AI-generated figure is included."
        ),
    )


def snapshot_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
