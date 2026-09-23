"""Search endpoints: adaptive, inventory-driven result sections + near-me.

Every section count comes from an actual query against MongoDB. No
hardcoded numbers and no fabricated sections (see search_sections_service).
"""
from __future__ import annotations

from typing import Optional
from datetime import datetime, timezone
import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.security import get_current_user, get_optional_user
from app.core.config import settings
from app.schemas import (
    PropertyListResponse,
    SearchSectionsResponse,
    UnifiedSearchRequest,
    UnifiedSearchResponse,
    WebDiscoveryCard,
    WebDiscoveryDetail,
    WebDiscoverySaveResponse,
)
from app.schemas.ai import SearchIntent
from app.services.property_service import PropertyService
from app.services.search_sections_service import SearchSectionsService
from app.ai.query_parser import parse_query
from app.models.user import User

router = APIRouter(prefix="/search", tags=["Search"])


class NearMeRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(5.0, gt=0, le=100)
    q: Optional[str] = None
    property_type: Optional[str] = None
    listing_type: Optional[str] = None


@router.get("/sections", response_model=SearchSectionsResponse)
async def get_search_sections(
    q: Optional[str] = Query(None, description="Text search"),
    city: Optional[str] = Query(None),
    locality: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
    listing_type: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    bedrooms: Optional[int] = Query(None, ge=0),
    min_bedrooms: Optional[int] = Query(None, ge=0),
    max_bedrooms: Optional[int] = Query(None, ge=0),
    bathrooms: Optional[int] = Query(None, ge=0),
    min_area: Optional[float] = Query(None, ge=0),
    max_area: Optional[float] = Query(None, ge=0),
    furnishing: Optional[str] = Query(None),
    amenities: Optional[list[str]] = Query(None),
    parking: Optional[int] = Query(None, ge=0),
    min_floor: Optional[int] = Query(None, ge=0),
    max_floor: Optional[int] = Query(None, ge=0),
    latitude: Optional[float] = Query(None, ge=-90, le=90),
    longitude: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: Optional[float] = Query(None, gt=0, le=100),
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Return dynamic sections where every count comes from a real query."""
    if any(value is not None for value in (latitude, longitude, radius_km)) and not all(
        value is not None for value in (latitude, longitude, radius_km)
    ):
        raise HTTPException(status_code=422, detail="latitude, longitude and radius_km must be provided together")

    params = {
        "q": q, "city": city, "locality": locality, "property_type": property_type,
        "listing_type": listing_type, "min_price": min_price, "max_price": max_price,
        "bedrooms": bedrooms, "min_bedrooms": min_bedrooms, "max_bedrooms": max_bedrooms,
        "bathrooms": bathrooms, "min_area": min_area, "max_area": max_area,
        "furnishing": furnishing, "amenities": amenities, "parking": parking,
        "min_floor": min_floor, "max_floor": max_floor,
        "latitude": latitude, "longitude": longitude, "radius_km": radius_km,
    }
    user_id = current_user.id if current_user else None
    return SearchSectionsService(db).build_sections(params, user_id=user_id)


@router.get("/parse", response_model=SearchIntent)
async def parse_search_query(q: str = Query(..., min_length=1, max_length=500)):
    """Return the validated SearchIntent extracted from a natural-language query.

    The UI uses this to surface interpreted chips (city, budget, BHK, listing
    type) before a search runs. Pure derivation — no results are returned here.
    """
    return parse_query(q)


@router.post("/near-me", response_model=PropertyListResponse)
async def search_near_me(
    req: NearMeRequest,
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Search properties near the user's explicit location permission result."""
    service = PropertyService(db)
    return service.search_properties(
        user_id=current_user.id if current_user else None,
        q=req.q,
        latitude=req.latitude,
        longitude=req.longitude,
        radius_km=req.radius_km,
        property_type=req.property_type,
        listing_type=req.listing_type,
        page=1,
        page_size=20,
    )


# ─── Unified search (verified inventory + web discoveries) ─────────────────

@router.post("", response_model=UnifiedSearchResponse)
@router.post("/autonomous", response_model=UnifiedSearchResponse)
async def unified_search(
    data: UnifiedSearchRequest,
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Combined search: verified inventory (MongoDB) + web discoveries.

    The two result sets are kept strictly separate — verified_properties vs
    web_discoveries — so the UI and AI can never confuse them. Web discovery is
    bounded (max 3 provider queries, max results per request, cached) and
    returns typed WEB_SEARCH_NOT_CONFIGURED / WEB_SEARCH_UNAVAILABLE states.
    """
    import asyncio
    import time

    from app.discovery.service import WebDiscoveryService
    from app.services.ai_search_service import AiSearchService
    from app.schemas.discovery import SearchMetadata, UnifiedSearchResponse

    started = time.perf_counter()
    intent = parse_query(data.query)
    user_id = current_user.id if current_user else None

    # 1) Verified inventory — deterministic MongoDB-first discovery.
    verified = AiSearchService(db).search(data.query, data.limit, data.filters)
    verified_properties = [item.model_dump() for item in verified["results"]]

    # 2) Web discovery — bounded provider search in a thread (never the event loop).
    web_latency_ms = 0.0
    web_discoveries: list = []
    web_total = 0
    web_metadata = {"web_search_used": False}
    from app.discovery.repository import SavedDiscoveryRepository

    saved_ids: set[str] = set()
    if user_id:
        for row in SavedDiscoveryRepository(db).list_for_user(user_id, limit=200):
            saved_ids.add(str(row.get("discovery_id")))

    web_outcome = None
    if data.include_web:
        from app.providers.web_search.limiter import get_web_search_limiter
        from app.providers.web_search.models import WebSearchRateLimitError

        limiter = get_web_search_limiter()
        limiter_held = False
        try:
            limiter.acquire(user_key=f"user_{user_id or 'anonymous'}")
            limiter_held = True
        except WebSearchRateLimitError as exc:
            raise HTTPException(status_code=429, detail=exc.message)
        web_started = time.perf_counter()
        service = WebDiscoveryService(db)
        web_outcome = await asyncio.to_thread(
            service.discover,
            intent,
            max_queries=settings.WEB_SEARCH_MAX_QUERIES,
            max_results=settings.WEB_SEARCH_MAX_RESULTS,
            saved_ids=saved_ids,
        )
        web_latency_ms = round((time.perf_counter() - web_started) * 1000, 1)
        if limiter_held:
            limiter.release()
        web_discoveries = web_outcome.cards
        web_total = len(web_discoveries)
        web_metadata = {
            "web_search_used": web_outcome.status == "available",
            "provider": web_outcome.provider,
            "provider_status": web_outcome.status,
            "web_message": web_outcome.message,
            "cache_hit": web_outcome.cache_hit,
            "stale_cache_used": web_outcome.stale_cache_used,
            "queries_used": web_outcome.queries_used,
        }
        # Compact operational telemetry: no token, password, or raw provider
        # payload is persisted. It lets operators distinguish a cache hit,
        # provider outage, or genuinely empty search without inventing data.
        db["discovery_runs"].insert_one({
            "query_hash": hashlib.sha256(data.query.strip().casefold().encode("utf-8")).hexdigest(),
            "category": getattr(intent, "category", "PROPERTY_SALE"),
            "provider": web_outcome.provider,
            "status": web_outcome.status,
            "code": web_outcome.code,
            "cache_hit": web_outcome.cache_hit,
            "stale_cache_used": web_outcome.stale_cache_used,
            "queries_count": len(web_outcome.queries_used),
            "sources_count": len(web_outcome.sources_searched),
            "results_count": len(web_outcome.cards),
            "inserted_count": web_outcome.inserted,
            "duration_ms": web_outcome.duration_ms,
            "started_at": datetime.now(timezone.utc),
        })
    # 3) Verified dynamic sections (counts come from real MongoDB queries).
    section_params = {k: v for k, v in data.filters.items() if v not in (None, "")}
    section_params.setdefault("q", data.query)
    sections_response = SearchSectionsService(db).build_sections(
        section_params, user_id=user_id
    )
    sections = [section.model_dump() for section in sections_response["sections"]]

    facets = {
        "verified_total": verified["total"],
        "web_total": web_total,
        "property_types": _facet_counts(verified_properties, "property_type"),
        "cities": _facet_counts(verified_properties, "city"),
    }

    latency_ms = {"total_ms": round((time.perf_counter() - started) * 1000, 1), "web_ms": web_latency_ms}
    if verified.get("metrics"):
        latency_ms["database_ms"] = verified["metrics"].get("database_latency_ms")
        latency_ms["location_ms"] = verified["metrics"].get("location_latency_ms")

    return UnifiedSearchResponse(
        query=data.query,
        parsed=intent.model_dump(),
        verified_properties=verified_properties,
        verified_total=verified["total"],
        web_discoveries=[WebDiscoveryCard.model_validate(item) for item in web_discoveries],
        web_total=web_total,
        sections=sections,
        facets=facets,
        metadata=SearchMetadata(
            web_search_used=bool(web_metadata.get("web_search_used")),
            provider=web_metadata.get("provider"),
            provider_status=web_metadata.get("provider_status"),
            cache_hit=bool(web_metadata.get("cache_hit")),
            stale_cache_used=bool(web_metadata.get("stale_cache_used")),
            queries_used=web_metadata.get("queries_used") or [],
            counts={"verified": verified["total"], "web": web_total},
            web_message=web_metadata.get("web_message"),
            latency_ms=latency_ms,
        ),
    )


def _facet_counts(items, key: str) -> dict:
    counts: dict = {}
    for item in items:
        value = item.get(key)
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts


# ─── Web discovery detail + save ────────────────────────────────────────────

@router.get("/discoveries/{discovery_id}", response_model=WebDiscoveryDetail)
async def discovery_detail(
    discovery_id: str,
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Full web-discovery record (never presented as a verified property)."""
    from app.discovery.repository import SavedDiscoveryRepository, WebDiscoveryRepository
    from app.discovery.service import doc_to_card

    repo = WebDiscoveryRepository(db)
    doc = repo.by_id(discovery_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Discovery not found (it may have expired).")

    saved = False
    if current_user:
        saved = SavedDiscoveryRepository(db).is_saved(current_user.id, discovery_id)
    card = doc_to_card(doc, saved=saved)
    card["query"] = doc.get("query")
    card["query_hash"] = doc.get("query_hash")
    card["source_listing_id"] = doc.get("source_listing_id")
    raw = doc.get("raw_metadata") or {}
    card["raw_metadata_summary"] = {
        key: raw[key] for key in ("page_age", "age", "language", "profile", "extra_snippets")
        if key in raw
    } or None
    return WebDiscoveryDetail(**card)


@router.post("/discoveries/{discovery_id}/save", response_model=WebDiscoverySaveResponse)
async def save_discovery(
    discovery_id: str,
    db = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save a web discovery for later — distinct from a verified saved property."""
    from app.discovery.repository import SavedDiscoveryRepository, WebDiscoveryRepository

    repo = WebDiscoveryRepository(db)
    if repo.by_id(discovery_id) is None:
        raise HTTPException(status_code=404, detail="Discovery not found (it may have expired).")
    SavedDiscoveryRepository(db).save(current_user.id, discovery_id)
    return WebDiscoverySaveResponse(
        discovery_id=discovery_id, saved=True,
        message="Saved web discovery (not a verified property — check the source link before relying on it).",
    )


@router.delete("/discoveries/{discovery_id}/save", response_model=WebDiscoverySaveResponse)
async def unsave_discovery(
    discovery_id: str,
    db = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.discovery.repository import SavedDiscoveryRepository

    removed = SavedDiscoveryRepository(db).unsave(current_user.id, discovery_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Saved discovery not found")
    return WebDiscoverySaveResponse(discovery_id=discovery_id, saved=False, message="Saved discovery removed")
