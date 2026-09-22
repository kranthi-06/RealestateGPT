"""RealEstateGPT - Typed AI agent tools.

Every tool has a Pydantic-validated input, returns serializable output built
from application data only. Tools never execute arbitrary code and never query
the database directly - they delegate to repositories and services.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from pydantic import BaseModel, Field

from app.finance.calculators import (
    calculate_affordability, calculate_emi, calculate_rental_yield, calculate_roi,
)
from app.location.service import LocationService, haversine_km
from app.repositories.property_repo import PropertyRepository
from app.services.finance_service import FinanceService

logger = logging.getLogger(__name__)


# ─── Tool input schemas ────────────────────────────────────────────────

class SearchInput(BaseModel):
    query: str = Field("", description="Natural-language property request")
    city: Optional[str] = None
    locality: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = Field(None, ge=0, le=20)
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    limit: int = Field(8, ge=1, le=20)


class PropertyIdsInput(BaseModel):
    property_ids: List[int] = Field(..., min_length=1, max_length=4)


class NearbyInput(BaseModel):
    property_id: int
    place_type: Optional[str] = None
    radius_km: float = Field(3.0, ge=0.1, le=50)


class DistanceInput(BaseModel):
    from_lat: float = Field(ge=-90, le=90)
    from_lon: float = Field(ge=-180, le=180)
    to_lat: float = Field(ge=-90, le=90)
    to_lon: float = Field(ge=-180, le=180)


class RouteInput(DistanceInput):
    travel_mode: str = Field(default="DRIVE", pattern="^(DRIVE|WALK|BICYCLE)$")


class EstimateInput(BaseModel):
    property_id: int


class EmiInput(BaseModel):
    principal: float = Field(gt=0)
    annual_interest_rate: float = Field(gt=0, le=50)
    tenure_years: float = Field(gt=0, le=40)


class AffordInput(BaseModel):
    monthly_income: float = Field(gt=0)
    existing_obligations: float = Field(0, ge=0)
    down_payment: float = Field(0, ge=0)
    property_price: Optional[float] = Field(None, gt=0)
    annual_interest_rate: float = Field(7.5, gt=0, le=50)
    tenure_years: float = Field(20, gt=0, le=40)


class YieldInput(BaseModel):
    property_price: float = Field(gt=0)
    monthly_rent: float = Field(gt=0)
    annual_expenses_pct: float = Field(0, ge=0, le=100)


class RoiInput(BaseModel):
    purchase_price: float = Field(gt=0)
    annual_rent: float = Field(0, ge=0)
    annual_expenses: float = Field(0, ge=0)
    appreciation_pct: float = Field(6, ge=-50, le=100)
    years: int = Field(5, ge=1, le=30)


class DocumentIdInput(BaseModel):
    document_id: int
    question: Optional[str] = Field(None, max_length=2000)


class SavePropertyInput(BaseModel):
    property_id: int
    notes: Optional[str] = Field(None, max_length=1000)

class SearchWebInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    city: Optional[str] = None
    locality: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = Field(None, ge=0, le=20)
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    limit: int = Field(8, ge=1, le=20)

@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    requires_auth: bool
    execute: Callable[..., dict]


def _serialize_prop(prop) -> dict:
    return {
        "id": prop.id,
        "title": prop.title,
        "slug": prop.slug,
        "price": prop.price,
        "price_per_sqft": prop.price_per_sqft,
        "property_type": prop.property_type,
        "listing_type": prop.listing_type,
        "bedrooms": prop.bedrooms,
        "bathrooms": prop.bathrooms,
        "area_sqft": prop.area_sqft,
        "locality": prop.locality,
        "city": prop.city,
        "builder_name": prop.builder_name,
        "verification_status": prop.verification_status,
        "is_synthetic": prop.is_synthetic,
        "amenities": [a.name for a in (prop.amenities or [])],
    }


def _tool_search(db, user, parsed: SearchInput, **kwargs) -> dict:
    from app.services.ai_search_service import AiSearchService

    filters = {
        "city": parsed.city, "locality": parsed.locality,
        "property_type": parsed.property_type, "bedrooms": parsed.bedrooms,
        "min_price": parsed.min_price, "max_price": parsed.max_price,
    }
    filters = {k: v for k, v in filters.items() if v is not None}
    service = AiSearchService(db)
    result = service.search(parsed.query or "", limit=parsed.limit, user_filters=filters)
    return result


def _tool_get_property(db, user, parsed: PropertyIdsInput) -> dict:
    repo = PropertyRepository(db)
    props = repo.get_by_ids(parsed.property_ids)
    return {"properties": [_serialize_prop(p) for p in props]}


def _tool_compare(db, user, parsed: PropertyIdsInput) -> dict:
    repo = PropertyRepository(db)
    props = repo.get_by_ids(parsed.property_ids)
    finance = FinanceService(db)
    items = []
    for p in props:
        item = _serialize_prop(p)
        try:
            item["estimate"] = finance.estimate(p.id)
        except Exception:  # noqa: BLE001
            item["estimate"] = None
        items.append(item)
    return {"comparison": items, "property_ids": parsed.property_ids}


def _tool_nearby(db, user, parsed: NearbyInput) -> dict:
    location = LocationService(db)
    if parsed.place_type:
        places = location.nearby(parsed.property_id, parsed.place_type, parsed.radius_km)
        return {"place_type": parsed.place_type, "radius_km": parsed.radius_km, "places": places}
    context = location.property_context(parsed.property_id)
    return {"places": context.get("all_places", []), "categories": context.get("categories", [])}

def _tool_search_web(db, user, parsed: SearchWebInput) -> dict:
    """Bounded web discovery through the backend (never arbitrary browsing).

    Returns normalized candidates only. The AI receives the SAME shape the
    frontend cards use and must cite results by ``result_id`` (e.g. WEB-001).
    """
    from app.ai.query_parser import parse_query
    from app.core.config import settings
    from app.discovery.service import WebDiscoveryService
    from app.providers.web_search.models import WebSearchNotConfiguredError, WebSearchUnavailableError

    intent = parse_query(parsed.query or "")
    if not intent.city and parsed.city:
        intent.city = parsed.city
    if not intent.locality and parsed.locality:
        intent.locality = parsed.locality
    try:
        outcome = WebDiscoveryService(db).discover(
            intent,
            max_queries=settings.WEB_SEARCH_MAX_QUERIES,
            max_results=min(parsed.limit, settings.WEB_SEARCH_MAX_RESULTS),
            enrich=False,
        )
    except (WebSearchNotConfiguredError, WebSearchUnavailableError) as exc:
        return {"status": "unavailable", "code": exc.code, "message": exc.message, "results": []}

    results = []
    for index, card in enumerate(outcome.cards[: parsed.limit]):
        results.append({
            "result_id": f"WEB-{index + 1:03d}",
            "discovery_id": card.get("id"),
            "title": card.get("title"),
            "price": card.get("price"),
            "currency": card.get("currency"),
            "transaction_type": card.get("transaction_type"),
            "bedrooms": card.get("bedrooms"),
            "area": card.get("area"),
            "area_unit": card.get("area_unit"),
            "location": card.get("location_text") or card.get("locality") or card.get("city"),
            "source": card.get("source_name") or card.get("source_domain"),
            "source_domain": card.get("source_domain"),
            "url": card.get("url"),
            "description": card.get("description"),
            "confidence": card.get("confidence"),
            "freshness_label": card.get("freshness_label"),
            "verification_status": "web_discovery",  # NEVER verified inventory
        })
    return {
        "status": outcome.status,
        "code": outcome.code,
        "message": outcome.message,
        "provider": outcome.provider,
        "sources_searched": outcome.sources_searched,
        "total": len(results),
        "results": results,
        "meta": {
            "cache_hit": outcome.cache_hit,
            "stale_cache_used": outcome.stale_cache_used,
            "queries_used": outcome.queries_used,
        },
    }


def _tool_distance(db, user, parsed: DistanceInput) -> dict:
    return {
        "distance_km": haversine_km(parsed.from_lat, parsed.from_lon,
                                    parsed.to_lat, parsed.to_lon),
        "formula": "haversine",
    }


def _tool_route(db, user, parsed: RouteInput) -> dict:
    """Route through the configured provider; never substitute a distance estimate."""
    location = LocationService(db)
    return location.provider.route(
        (parsed.from_lat, parsed.from_lon), (parsed.to_lat, parsed.to_lon), parsed.travel_mode,
    )


def _tool_document_analysis(db, user, parsed: DocumentIdInput) -> dict:
    if not user:
        raise PermissionError("Authentication required")
    from app.repositories.platform_repo import DocumentRepository

    repo = DocumentRepository(db)
    doc = repo.get(parsed.document_id, user.id)
    if not doc:
        raise ValueError("document_not_found")
    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "preview": (doc.text_preview or "")[:500],
        "note": "Deep document Q&A runs through the document pipeline (later phase).",
    }


def _tool_document_search(db, user, parsed: PropertyIdsInput) -> dict:
    if not user:
        raise PermissionError("Authentication required")
    from app.repositories.platform_repo import DocumentRepository

    repo = DocumentRepository(db)
    docs = repo.list_for_user(user.id)
    return {
        "documents": [
            {"id": d.id, "filename": d.filename, "status": d.status,
             "property_id": d.property_id, "preview": (d.text_preview or "")[:200]}
            for d in docs
            if d.property_id in parsed.property_ids or not parsed.property_ids
        ]
    }


def _tool_save_property(db, user, parsed: SavePropertyInput) -> dict:
    if not user:
        raise PermissionError("Authentication required")
    from app.repositories.saved_repo import SavedRepository

    repo = SavedRepository(db)
    saved = repo.save_property(user.id, parsed.property_id, parsed.notes)
    return {"id": saved.id, "property_id": parsed.property_id, "message": "Property saved"}


def _tool_save_search(db, user, parsed: SearchInput) -> dict:
    if not user:
        raise PermissionError("Authentication required")
    from app.repositories.saved_repo import SavedRepository

    repo = SavedRepository(db)
    saved = repo.save_search(
        user_id=user.id,
        name=(parsed.query or "AI search")[:80],
        city=parsed.city, locality=parsed.locality, property_type=parsed.property_type,
        bedrooms=parsed.bedrooms, min_price=parsed.min_price, max_price=parsed.max_price,
        query_text=parsed.query,
    )
    return {"id": saved.id, "message": "Search saved"}


TOOLS: List[Tool] = [
    Tool("search_properties",
         "Search the property catalogue with filters or natural language and return ranked matches with match scores.",
         SearchInput, False, _tool_search),
    Tool("search_web_properties",
         "Discover property listings from the web via the configured search provider (bounded, cached). "
         "Results are WEB-DISCOVERED, never verified inventory; cite them by result_id (e.g. WEB-001) and "
         "never invent prices, area, BHK or availability that the returned fields do not contain.",
         SearchWebInput, False, _tool_search_web),
    Tool("get_property",
         "Fetch full details for one or more properties by ID.",
         PropertyIdsInput, False, _tool_get_property),
    Tool("compare_properties",
         "Compare 2-4 properties on price, size, price/sqft and estimated value.",
         PropertyIdsInput, False, _tool_compare),
    Tool("find_nearby_places",
         "List places (metro, hospital, school, mall, park, airport, IT park) near a property.",
         NearbyInput, False, _tool_nearby),
    Tool("calculate_distance",
         "Haversine distance between two coordinates in km.",
         DistanceInput, False, _tool_distance),
    Tool("calculate_route",
         "Calculate actual provider route distance and duration between two coordinates.",
         RouteInput, False, _tool_route),
    Tool("estimate_property_price",
         "ML estimate of a property's market price range.",
         EstimateInput, False, lambda db, user, parsed: _tool_estimate(db, user, parsed)),
    Tool("calculate_affordability",
         "Compute affordable loan amount and EMI from monthly income.",
         AffordInput, False, lambda db, user, parsed: _tool_affordability(db, user, parsed)),
    Tool("calculate_emi",
         "Compute monthly EMI for a loan.",
         EmiInput, False, lambda db, user, parsed: _tool_emi(db, user, parsed)),
    Tool("calculate_rental_yield",
         "Compute gross/net rental yield for a property.",
         YieldInput, False, lambda db, user, parsed: _tool_yield(db, user, parsed)),
    Tool("calculate_roi",
         "Project investment return over N years.",
         RoiInput, False, lambda db, user, parsed: _tool_roi(db, user, parsed)),
    Tool("analyze_property_document",
         "Analyze a user's uploaded property document (PDF).",
         DocumentIdInput, True, _tool_document_analysis),
    Tool("search_property_documents",
         "List documents the user uploaded for given properties.",
         PropertyIdsInput, True, _tool_document_search),
    Tool("save_property",
         "Save a property to the user's saved list.",
         SavePropertyInput, True, _tool_save_property),
    Tool("save_search",
         "Save the current search for later.",
         SearchInput, True, _tool_save_search),
]

_BY_NAME = {t.name: t for t in TOOLS}


def get_tool(name: str) -> Optional[Tool]:
    return _BY_NAME.get(name)


def execute_tool(db, user, name: str, raw_input: dict) -> dict:
    tool = get_tool(name)
    if tool is None:
        raise ValueError(f"unknown_tool:{name}")
    if tool.requires_auth and user is None:
        raise PermissionError("Authentication required for this tool")
    validated = tool.input_model.model_validate(raw_input)
    return tool.execute(db, user, validated)


def list_tool_descriptions() -> List[dict]:
    return [
        {"name": t.name, "description": t.description,
         "parameters": t.input_model.model_json_schema()}
        for t in TOOLS
    ]


def _tool_estimate(db, user, parsed: EstimateInput) -> dict:
    finance = FinanceService(db)
    try:
        return finance.estimate(parsed.property_id)
    except ValueError:
        raise ValueError("property_not_found")


def _tool_emi(db, user, parsed: EmiInput) -> dict:
    return calculate_emi(parsed.principal, parsed.annual_interest_rate, parsed.tenure_years)


def _tool_affordability(db, user, parsed: AffordInput) -> dict:
    return calculate_affordability(
        parsed.monthly_income, parsed.existing_obligations, parsed.down_payment,
        parsed.annual_interest_rate, parsed.tenure_years, 0.5,
    )


def _tool_yield(db, user, parsed: YieldInput) -> dict:
    return calculate_rental_yield(parsed.property_price, parsed.monthly_rent,
                                  parsed.annual_expenses_pct)


def _tool_roi(db, user, parsed: RoiInput) -> dict:
    return calculate_roi(parsed.purchase_price, parsed.annual_rent,
                         parsed.annual_expenses, parsed.appreciation_pct, parsed.years)
