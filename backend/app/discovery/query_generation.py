"""Bounded web-search query generation from a parsed SearchIntent.

Never sends the raw user query blindly. Derives up to
``WEB_SEARCH_MAX_QUERIES`` distinct, property-focused queries from the typed
intent, capped so we never paginate through the entire internet.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.schemas.ai import SearchIntent

logger = logging.getLogger(__name__)

_PROPERTY_TYPE_LABELS = {
    "apartment": "apartments",
    "villa": "villas",
    "plot": "plots",
    "independent_house": "houses",
    "studio": "studio apartments",
    "penthouse": "penthouses",
}

_CATEGORY_LABELS = {
    "HOTEL": "hotels", "HOSTEL": "hostels", "SHORT_STAY": "short stays",
    "VACATION_RENTAL": "vacation rentals", "SERVICED_APARTMENT": "serviced apartments",
    "PG": "PG accommodation", "CO_LIVING": "co-living accommodation",
    "ACCOMMODATION": "accommodation",
}

_NEARBY_LABELS = {
    "metro": "near metro",
    "hospital": "near hospital",
    "school": "near school",
    "supermarket": "near supermarket",
    "it_park": "near IT park",
    "mall": "near mall",
    "airport": "near airport",
    "transport": "near bus stop",
}


def _budget_phrase(intent: SearchIntent) -> Optional[str]:
    if not intent.max_price:
        return None
    value = float(intent.max_price)
    if value >= 10_000_000:
        label = f"{value / 10_000_000:g} crore"
    elif value >= 100_000:
        label = f"{value / 100_000:g} lakh"
    else:
        label = f"{int(value)}"
    return f"under {label}"


def _bedroom_phrase(intent: SearchIntent) -> Optional[str]:
    if intent.bedrooms is None:
        return None
    return f"{int(intent.bedrooms)} BHK"


def _transaction_phrase(intent: SearchIntent) -> str:
    return "for rent" if intent.listing_type == "rent" else "for sale"


def _accommodation_phrase(intent: SearchIntent) -> Optional[str]:
    label = _CATEGORY_LABELS.get(getattr(intent, "category", ""))
    if not label:
        return None
    details = [label]
    if intent.guests:
        details.append(f"for {intent.guests} guests")
    if intent.rooms:
        details.append(f"{intent.rooms} rooms")
    if intent.breakfast_required:
        details.append("breakfast")
    return " ".join(details)


def _place_phrase(intent: SearchIntent) -> Optional[str]:
    if intent.locality and intent.city:
        return f"{intent.locality}, {intent.city}"
    return intent.city or intent.locality


def _nearby_phrase(intent: SearchIntent) -> Optional[str]:
    for req in intent.nearby_requirements or []:
        label = _NEARBY_LABELS.get(req.type, f"near {req.type.replace('_', ' ')}")
        if label:
            return label
    if intent.transport_requirement:
        return f"near {intent.transport_requirement}"
    return None


def _type_phrase(intent: SearchIntent) -> Optional[str]:
    return _PROPERTY_TYPE_LABELS.get(intent.property_type, intent.property_type) if intent.property_type else None


def _join(parts: list[Optional[str]]) -> str:
    return " ".join(part for part in parts if part).strip()


def build_search_queries(intent: SearchIntent, max_queries: int = 3) -> list[str]:
    """Build a bounded, deduplicated list of web search queries.

    1. Most complete variant (BHK + type + transaction + budget + place).
    2. Location/nearby variant (same core, place + "near X").
    3. Keyword/localized fallback when slots and distinct angles remain.
    """
    max_queries = max(1, min(int(max_queries), 8))
    bhk = _bedroom_phrase(intent)
    ptype = _type_phrase(intent)
    accommodation = _accommodation_phrase(intent)
    txn = "" if accommodation else _transaction_phrase(intent)
    budget = _budget_phrase(intent)
    place = _place_phrase(intent)
    nearby = _nearby_phrase(intent)

    queries: list[str] = []

    core = _join([accommodation, bhk, ptype, txn])
    if not core:
        core = "property for sale" if intent.listing_type != "rent" else "rental properties"

    # 1) Primary: core + budget + place.
    primary = _join([core, budget])
    if place:
        primary = _join([primary, "in", place])
    if primary not in queries:
        queries.append(primary)

    # 2) Nearby variant (no budget — search engines handle locality better).
    if nearby:
        nearby_q = _join([core, "in", place] if place else [core])
        if nearby not in nearby_q.split():
            nearby_q = _join([nearby_q, nearby])
        if nearby_q != primary and nearby_q not in queries:
            queries.append(nearby_q)

    base_words = set((primary + " " + core).lower().split())

    # 3) Keyword/localized fallback.
    if len(queries) < max_queries and intent.locality:
        localized = _join([core, budget, "in", f"{intent.locality}, {intent.city or ''}"])
        if localized != primary and localized not in queries:
            queries.append(localized)
    for token in (intent.keywords or [])[:5]:
        if len(queries) >= max_queries:
            break
        token_lower = token.lower()
        if token_lower in base_words or token.isdigit():
            continue
        candidate = _join([token, core, budget])
        if candidate != primary and candidate not in queries:
            queries.append(candidate)

    # 4) Plain place + transaction bail-out while slots remain.
    if len(queries) < max_queries and place:
        bail = _join([txn, "in", place])
        if bail not in queries:
            queries.append(bail)

    return queries[:max_queries]
