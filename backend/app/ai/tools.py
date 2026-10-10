"""RealEstateGPT - Typed AI agent tools.

Every tool has a Pydantic-validated input, returns serializable output built
from application data only. Tools never execute arbitrary code and never query
the database directly - they delegate to repositories and services.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from pydantic import BaseModel, Field, model_validator

from app.finance.calculators import (
    calculate_affordability, calculate_emi, calculate_full_affordability,
    calculate_rental_yield, calculate_roi,
)
from app.location.service import LocationService, haversine_km
from app.providers.web_search import get_web_search_provider
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
    property_price: Optional[float] = Field(None, gt=0, description="Explicit target price in INR")
    property_id: Optional[int] = Field(
        None, gt=0, description="Resolve the asking price from this catalogue property id"
    )
    savings: Optional[float] = Field(None, ge=0)
    monthly_rent: float = Field(0, ge=0)
    maintenance_monthly: float = Field(0, ge=0)
    property_tax_annual: float = Field(0, ge=0)
    insurance_annual: float = Field(0, ge=0)
    other_monthly: float = Field(0, ge=0)
    annual_interest_rate: float = Field(7.5, gt=0, le=50)
    tenure_years: float = Field(20, gt=0, le=40)

    @model_validator(mode="after")
    def exactly_one_price_source(self) -> "AffordInput":
        if self.property_price is not None and self.property_id is not None:
            raise ValueError("Provide either property_price or property_id, not both")
        return self


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
    property_id: int = Field(..., gt=0)
    notes: Optional[str] = Field(None, max_length=1000)


class UnsavePropertyInput(BaseModel):
    property_id: int = Field(..., gt=0)


class SavedListInput(BaseModel):
    limit: int = Field(8, ge=1, le=20)


class SearchWebInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    city: Optional[str] = None
    locality: Optional[str] = None
    state: Optional[str] = Field(None, max_length=100)
    property_type: Optional[str] = None
    bedrooms: Optional[int] = Field(None, ge=0, le=20)
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    limit: int = Field(8, ge=1, le=20)
    # Coordinates from the user's device / reverse geocoding. When both are
    # present the agent MUST prefer the location-aware web tool so results
    # are targeted at the user's actual area rather than a guessed city.
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)


class MarketStatsInput(BaseModel):
    """Market Intelligence lookup by city and/or locality (no city allow-list)."""
    city: Optional[str] = Field(None, max_length=100)
    locality: Optional[str] = Field(None, max_length=100)
    listing_type: Optional[str] = Field(None, pattern="^(sale|rent)$")
    property_type: Optional[str] = Field(None, max_length=50)
    bedrooms: Optional[int] = Field(None, ge=0, le=20)


class LocationNearbyInput(BaseModel):
    """Nearby facilities for an arbitrary place or coordinates (OSM/Overpass).

    Either a free-text ``location`` (geocoded through Nominatim, so any city,
    locality, landmark or address works) or explicit coordinates.
    """
    location: Optional[str] = Field(None, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    category: str = Field("hospital", pattern="^(metro|hospital|school|college|supermarket|mall|park|it_park|hotel|restaurant|bank|shopping|pharmacy|public_transport)$")
    radius_km: float = Field(3.0, ge=0.1, le=50)

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
    from app.providers.location import get_location_provider
    from app.providers.web_search.models import WebSearchNotConfiguredError, WebSearchUnavailableError

    if user is not None and parsed.latitude is not None and parsed.longitude is not None:
        try:
            provider = get_location_provider()
            reverse = provider.reverse_geocode(parsed.latitude, parsed.longitude)
            if reverse.get("city"):
                if not parsed.city:
                    parsed.city = reverse["city"]
                if not parsed.locality:
                    parsed.locality = reverse.get("suburb") or reverse.get("city")
                if not parsed.state and reverse.get("state"):
                    parsed.state = reverse["state"]
                if not parsed.query:
                    parsed.query = (
                        f"properties for sale near "
                        f"{reverse.get('formatted_address') or reverse['city']}"
                    )
        except Exception:
            pass
    query_str = parsed.query or f"properties in {parsed.city or ''} {parsed.locality or ''}".strip()
    intent = parse_query(query_str or "properties for sale")
    if parsed.city:
        intent.city = parsed.city
    if parsed.locality:
        intent.locality = parsed.locality
    # Carry the state through so small towns get a usable geographic scope.
    if getattr(parsed, "state", None):
        intent.state = parsed.state
    if parsed.property_type:
        intent.property_type = parsed.property_type
    if parsed.bedrooms is not None:
        intent.bedrooms = parsed.bedrooms
    if parsed.min_price is not None:
        intent.min_price = parsed.min_price
    if parsed.max_price is not None:
        intent.max_price = parsed.max_price

    service = WebDiscoveryService(db)
    try:
        outcome = service.discover(intent, max_results=parsed.limit)
    except (WebSearchNotConfiguredError, WebSearchUnavailableError) as exc:
        return {
            "status": "unavailable",
            "code": getattr(exc, "code", "WEB_SEARCH_UNAVAILABLE"),
            "message": str(exc),
            "results": [],
        }

    results = []
    for index, card in enumerate(outcome.cards[: parsed.limit]):
        card_dict = card.model_dump() if hasattr(card, "model_dump") else (card if isinstance(card, dict) else {})
        results.append({
            "result_id": f"WEB-{index + 1:03d}",
            "discovery_id": card_dict.get("id"),
            "title": card_dict.get("title"),
            "price": card_dict.get("price"),
            "currency": card_dict.get("currency"),
            "transaction_type": card_dict.get("transaction_type"),
            "bedrooms": card_dict.get("bedrooms"),
            "area": card_dict.get("area"),
            "area_unit": card_dict.get("area_unit"),
            "location": card_dict.get("location_text") or card_dict.get("locality") or card_dict.get("city"),
            "source": card_dict.get("source_name") or card_dict.get("source_domain"),
            "source_domain": card_dict.get("source_domain"),
            "url": card_dict.get("url"),
            "description": card_dict.get("description"),
            "confidence": card_dict.get("confidence"),
            "freshness_label": card_dict.get("freshness_label"),
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


def _tool_market_stats(db, user, parsed: MarketStatsInput) -> dict:
    """Market Intelligence: real aggregated statistics for a place.

    Every figure is measured from verified stored listings. When the sample is
    too small the response says so instead of returning an invented number.
    """
    from app.services.market_service import MarketFilter, MarketService

    if not parsed.city and not parsed.locality:
        return {
            "status": "invalid",
            "message": "Provide a city or locality to get market statistics.",
        }

    service = MarketService(db)
    snapshot = service.snapshot(
        MarketFilter(
            city=parsed.city,
            locality=parsed.locality,
            listing_type=parsed.listing_type,
            property_type=parsed.property_type,
            bedrooms=parsed.bedrooms,
        )
    )
    payload = snapshot.to_dict()

    if snapshot.total_listings == 0:
        payload["status"] = "no_data"
        payload["message"] = (
            "No verified listings are stored for this location, so no price "
            "statistics can be reported. Do not estimate prices for it."
        )
        return payload

    payload["status"] = "ok"
    payload["message"] = (
        f"Statistics measured from {snapshot.total_listings} verified stored "
        "listings. Figures flagged is_measured=false come from fewer than "
        f"{payload['coverage'].get('minimum_sample', 3)} listings and are "
        "indicative only."
    )
    return payload


def _tool_location_nearby(db, user, parsed: LocationNearbyInput) -> dict:
    """Nearby facilities for a place name or coordinates via the OSM provider."""
    from app.providers.location import (
        LocationProviderInvalidRequest,
        LocationProviderUnavailable,
        get_location_provider,
    )

    latitude, longitude = parsed.latitude, parsed.longitude
    resolved = None
    if latitude is None or longitude is None:
        if not parsed.location:
            return {
                "status": "invalid",
                "message": "Provide a location name or coordinates.",
            }
        try:
            geo = get_location_provider().geocode(parsed.location)
        except (LocationProviderUnavailable, LocationProviderInvalidRequest) as exc:
            return {"status": "unavailable", "message": str(exc), "places": []}
        latitude, longitude = geo.get("latitude"), geo.get("longitude")
        resolved = geo.get("formatted_address")
        if latitude is None or longitude is None:
            return {
                "status": "not_found",
                "message": f"Could not geocode '{parsed.location}'.",
                "places": [],
            }

    try:
        places = get_location_provider().nearby(
            latitude, longitude, parsed.category, parsed.radius_km
        )
    except (LocationProviderUnavailable, LocationProviderInvalidRequest) as exc:
        return {
            "status": "unavailable",
            "message": str(exc),
            "places": [],
            "category": parsed.category,
            "radius_km": parsed.radius_km,
        }

    return {
        "status": "ok",
        "resolved_location": resolved or f"{latitude:.4f},{longitude:.4f}",
        "category": parsed.category,
        "radius_km": parsed.radius_km,
        "latitude": latitude,
        "longitude": longitude,
        "count": len(places),
        "places": [
            {
                "name": p.get("name"),
                "address": p.get("address"),
                "distance_km": p.get("distance_km"),
                "latitude": p.get("latitude"),
                "longitude": p.get("longitude"),
                "categories": p.get("categories"),
            }
            for p in places
        ],
        "message": (
            f"Found {len(places)} {parsed.category} place(s) within "
            f"{parsed.radius_km} km from OpenStreetMap/Overpass."
        ),
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
    existing = repo.is_saved(user.id, parsed.property_id)
    saved = repo.save_property(user.id, parsed.property_id, parsed.notes)
    return {
        "id": saved.id,
        "property_id": parsed.property_id,
        "already_saved": existing,
        "message": "Property already saved" if existing else "Property saved",
    }


def _tool_unsave_property(db, user, parsed: UnsavePropertyInput) -> dict:
    if not user:
        raise PermissionError("Authentication required")
    from app.repositories.saved_repo import SavedRepository

    repo = SavedRepository(db)
    removed = repo.unsave_property(user.id, parsed.property_id)
    return {
        "property_id": parsed.property_id,
        "removed": removed,
        "message": "Property removed from your saved list" if removed
                   else "That property was not in your saved list",
    }


def _tool_list_saved(db, user, parsed: SavedListInput) -> dict:
    """The signed-in user's own saved properties. Never another user's."""
    if not user:
        raise PermissionError("Authentication required")
    from app.repositories.saved_repo import SavedRepository

    repo = SavedRepository(db)
    items = [item for item in repo.get_saved_properties(user.id) if item.property is not None]
    return {
        "total": len(items),
        "results": [
            {
                "property_id": item.property.id,
                "title": item.property.title,
                "price": item.property.price,
                "city": item.property.city,
                "locality": item.property.locality,
                "bedrooms": item.property.bedrooms,
                "area_sqft": item.property.area_sqft,
                "price_per_sqft": item.property.price_per_sqft,
                "saved_at": item.created_at,
            }
            for item in items[: parsed.limit]
        ],
    }


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


def _tool_estimate(db, user, parsed: EstimateInput) -> dict:
    finance = FinanceService(db)
    try:
        return finance.estimate(parsed.property_id)
    except ValueError:
        raise ValueError("property_not_found")


def _tool_emi(db, user, parsed: EmiInput) -> dict:
    return calculate_emi(parsed.principal, parsed.annual_interest_rate, parsed.tenure_years)


def _tool_affordability(db, user, parsed: AffordInput) -> dict:
    """Full affordability assessment.

    When ``property_id`` is supplied the asking price is read from the catalogue
    so the calculation uses the real listing price rather than an LLM guess.
    """
    from app.repositories.property_repo import PropertyRepository

    property_price = parsed.property_price
    resolved_from = "user_input"
    if parsed.property_id and property_price is None:
        prop = PropertyRepository(db).get_by_id(parsed.property_id)
        if prop is None:
            return {
                "status": "not_found",
                "message": f"Property {parsed.property_id} is not in the catalogue.",
            }
        property_price = prop.price
        resolved_from = f"catalogue_property_{prop.id}"
    if property_price is None:
        base = calculate_affordability(
            parsed.monthly_income, parsed.existing_obligations, parsed.down_payment,
            parsed.annual_interest_rate, parsed.tenure_years, 0.5,
        )
        return {
            "status": "no_property",
            "price_source": "not_provided",
            **base,
            "message": (
                "No target property was provided, so only the maximum affordable "
                "loan/price could be calculated."
            ),
        }

    result = calculate_full_affordability(
        monthly_income=parsed.monthly_income,
        existing_obligations=parsed.existing_obligations,
        savings=parsed.savings or 0.0,
        down_payment=parsed.down_payment,
        property_price=property_price,
        monthly_rent=parsed.monthly_rent,
        maintenance_monthly=parsed.maintenance_monthly,
        property_tax_annual=parsed.property_tax_annual,
        insurance_annual=parsed.insurance_annual,
        other_monthly=parsed.other_monthly,
        annual_interest_rate=parsed.annual_interest_rate,
        tenure_years=parsed.tenure_years,
    )
    return {"status": "ok", "price_source": resolved_from, **result}


def _tool_yield(db, user, parsed: YieldInput) -> dict:
    return calculate_rental_yield(parsed.property_price, parsed.monthly_rent,
                                  parsed.annual_expenses_pct)


def _tool_roi(db, user, parsed: RoiInput) -> dict:
    return calculate_roi(parsed.purchase_price, parsed.annual_rent,
                         parsed.annual_expenses, parsed.appreciation_pct, parsed.years)


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
    Tool("get_market_stats",
         "Market Intelligence for a city and/or locality: apartment/house/plot prices, "
         "price per sq.ft and per sq.yard, typical rents, observed price changes, "
         "locality comparison and coverage metadata. Works for ANY location, not a fixed "
         "city list. Never use it to invent prices — report what the tool returns.",
         MarketStatsInput, False, _tool_market_stats),
    Tool("find_nearby_places_by_location",
         "List facilities (hospitals, schools, restaurants, transport, shopping, parks) near "
         "an arbitrary city, locality, landmark or address — geocoded via Nominatim — or near "
         "explicit coordinates. Use this when the user asks about facilities 'near this location' "
         "instead of near a specific saved property.",
         LocationNearbyInput, False, _tool_location_nearby),
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
         "Compute the maximum affordable loan/price AND, when a target property is given, the EMI, "
         "upfront costs, remaining income and remaining savings for that specific property. "
         "Pass property_id (not price) so the real asking price is used.",
         AffordInput, False, _tool_affordability),
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
         "Save a verified catalogue property to the user's saved list. Idempotent.",
         SavePropertyInput, True, _tool_save_property),
    Tool("unsave_property",
         "Remove a property from the user's saved list.",
         UnsavePropertyInput, True, _tool_unsave_property),
    Tool("list_saved_properties",
         "List the signed-in user's own saved properties with their real prices.",
         SavedListInput, True, _tool_list_saved),
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
