"""Market intelligence endpoints — location-based insights from stored data.

Honesty contract:
   * every catalogue figure is aggregated from verified listings in MongoDB;
   * statistics derived from a small sample are explicitly flagged
     (``is_measured``) so the UI never presents a guess as a market rate;
   * when there is not enough data the endpoint returns an explicit
     ``insufficient_data`` reason instead of inventing numbers;
   * external research (``/market/external``) is a SEPARATE data source: every
     observation carries its source URL, publication date and retrieval
     timestamp, and unavailable metrics are reported as unavailable.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import general_limiter
from app.core.security import get_optional_user
from app.schemas.market import (
    ExternalMarketRequest,
    ExternalMarketResponse,
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
    include_external: bool = Query(True),
    db=Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """Return price/rent/trend statistics for a searched city + locality.

    The search is free-text and not limited to any hardcoded city list; the
    filter is matched case-insensitively against stored ``city``/``locality``.

    When the catalogue has no (or too little) data for the location, external
    market research is attached under ``external`` so the dashboard can show
    sourced real-world observations instead of empty charts.
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

    # Catalogue statistics are non-personalized aggregates, so they can be
    # cached briefly and shared. The cache is invalidated when listings change.
    from app.core.cache import CacheRepository, cache_key, policy_for

    snapshot_key = cache_key(
        "market_snapshot",
        {
            "city": city, "locality": locality, "listing_type": _normalize_listing_type(listing_type),
            "property_type": property_type, "bedrooms": bedrooms,
            "min_price": min_price, "max_price": max_price, "history": include_history,
        },
    )
    cache = CacheRepository(db)
    entry = cache.get(snapshot_key)
    if entry is not None and not entry["is_error"]:
        payload = entry["payload"]
    else:
        snapshot = service.snapshot(flt, include_history=include_history)
        payload = snapshot.to_dict()
        cache.set(snapshot_key, payload, policy=policy_for("market_snapshot"))

    snapshot_total = payload.get("totals", {}).get("listings", 0)
    snapshot_sale = payload.get("totals", {}).get("sale", 0)
    if snapshot_total == 0:
        payload["insufficient_data"] = {
            "code": "NO_LISTINGS",
            "reason": (
                "No verified listings are stored for this location. "
                "Market statistics are not generated when there is no inventory to measure."
            ),
        }
    elif snapshot_sale < MIN_SAMPLE:
        payload["insufficient_data"] = {
            "code": "SALE_SAMPLE_TOO_SMALL",
            "reason": (
                f"Only {snapshot_sale} sale listing(s) are stored for this location; "
                f"at least {MIN_SAMPLE} are needed before price statistics are treated as measured."
            ),
        }

    if include_external and (city or locality):
        payload["external"] = _run_external_research(
            db,
            location=", ".join(part for part in (locality, city) if part),
            city=city,
            locality=locality,
            listing_type=_normalize_listing_type(listing_type),
            property_type=property_type,
            bedrooms=bedrooms,
        )

    return MarketSnapshotResponse(**payload)


def _run_external_research(
    db,
    *,
    location: str,
    city: Optional[str],
    locality: Optional[str],
    listing_type: Optional[str],
    property_type: Optional[str],
    bedrooms: Optional[int],
) -> dict:
    """Run bounded external market research; never break the catalogue response."""
    try:
        from app.services.external_market_service import (
            ExternalMarketService,
            MarketResearchFilter,
        )

        flt = MarketResearchFilter(
            location=location,
            city=city,
            locality=locality,
            listing_type=listing_type,
            property_type=property_type,
            bedrooms=bedrooms,
        )
        research = ExternalMarketService(db).research(flt)
        research.setdefault("data_class", "external_observation")
        return research
    except Exception as exc:  # noqa: BLE001 - external research is additive only
        logger.warning("external_market_research_failed location=%s err=%s", location, exc)
        return {
            "status": "unavailable",
            "message": "External market research is temporarily unavailable.",
            "data_class": "external_observation",
        }


@router.post("/external", response_model=ExternalMarketResponse)
async def market_external_research(
    data: ExternalMarketRequest,
    request: Request,
    db=Depends(get_db),
):
    """Retrieve external property-market information for ANY location.

    This endpoint is strictly separate from the verified catalogue: it returns
    sourced observations with source links, publication dates and retrieval
    timestamps, and reports 'Data unavailable' for metrics it cannot find.
    """
    client = request.client.host if request.client else "unknown"
    general_limiter.check(
        f"market_research:{client}",
        settings.MARKET_RESEARCH_RATE_LIMIT,
        settings.MARKET_RESEARCH_RATE_WINDOW,
        enabled=settings.RATE_LIMIT_ENABLED,
    )
    from app.services.external_market_service import (
        ExternalMarketService,
        MarketResearchFilter,
    )

    flt = MarketResearchFilter(
        location=data.location,
        city=data.city,
        locality=data.locality,
        country=data.country,
        listing_type=data.listing_type,
        property_type=data.property_type,
        bedrooms=data.bedrooms,
        currency=data.currency,
        language=data.language,
    )
    research = ExternalMarketService(db).research(flt)
    return ExternalMarketResponse(
        status=research.get("status", "unavailable"),
        message=research.get("message"),
        location_input=research.get("location_input", data.location),
        resolved=research.get("resolved") or {},
        sources=research.get("sources") or [],
        observations=research.get("observations") or [],
        statistics=research.get("statistics") or {},
        ai_summary=research.get("ai_summary"),
        queries_used=research.get("queries_used") or [],
        provider=research.get("provider"),
        cache=research.get("cache") or {},
        generated_at=research.get("generated_at") or datetime.now(timezone.utc).isoformat(),
    )


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


@router.get("/compare")
async def market_compare(
    cities: str = Query(..., description="Comma-separated city names (max 6)"),
    listing_type: Optional[str] = Query(None, pattern=SALE_RENT),
    property_type: Optional[str] = Query(None, max_length=50),
    bedrooms: Optional[int] = Query(None, ge=0, le=20),
    db=Depends(get_db),
):
    """Side-by-side city statistics for the comparison view.

    Every figure is measured from stored listings; cities with too small a
    sample are returned with ``is_measured: false`` so the UI can say so.
    """
    names = [c.strip() for c in cities.split(",") if c.strip()][:6]
    if not names:
        raise HTTPException(status_code=422, detail="Provide at least one city to compare.")

    service = MarketService(db)
    rows = []
    for name in names:
        snapshot = service.snapshot(MarketFilter(
            city=name,
            listing_type=_normalize_listing_type(listing_type),
            property_type=property_type,
            bedrooms=bedrooms,
        ), include_history=False)
        base = snapshot.apartment_prices if snapshot.apartment_prices.sample_size else snapshot.house_prices
        psf = snapshot.apartment_psf if snapshot.apartment_psf.sample_size else snapshot.house_psf
        rows.append({
            "city": name,
            "listings": snapshot.total_listings,
            "sale_listings": snapshot.sale_listings,
            "rent_listings": snapshot.rent_listings,
            "median_price": base.median,
            "mean_price": base.mean,
            "min_price": base.min,
            "max_price": base.max,
            "median_price_per_sqft": psf.median,
            "median_rent_monthly": snapshot.rents_monthly.median,
            "gross_rental_yield_pct": snapshot.gross_yield_pct,
            "price_to_rent_ratio": snapshot.price_to_rent_ratio,
            "sample_size": base.sample_size,
            "is_measured": base.is_measured,
            "localities": snapshot.localities[:12],
        })
    return {
        "generated_at": snapshot_now(),
        "source": "Verified stored listings (RealEstateGPT catalogue)",
        "minimum_sample": MIN_SAMPLE,
        "cities": rows,
        "note": (
            "Asking prices from stored listings only. These are not completed "
            "transaction prices. Small samples are flagged as not measured."
        ),
    }


def snapshot_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
