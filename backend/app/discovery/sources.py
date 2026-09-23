"""Explicit source policies and category-aware discovery routing.

Registration permits search-result *discovery* only. It never grants page
retrieval permission: every listed source defaults to ``page_fetch_allowed``
false until an operator records a lawful integration or documented permission.
Unknown domains are therefore discovery-only and are never fetched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PropertySource:
    name: str
    domain: str
    category: str
    categories: tuple[str, ...]
    country: str = "IN"
    enabled: bool = True
    discovery_allowed: bool = True
    page_fetch_allowed: bool = False
    structured_data_allowed: bool = False
    api_available: bool = False
    api_configured: bool = False
    requires_auth: bool = False
    robots_policy: str = "unknown"
    rate_limit: int = 1
    max_concurrency: int = 1
    timeout_seconds: int = 10
    cache_ttl_seconds: int = 1800
    attribution_required: bool = True
    source_url: Optional[str] = None
    requires_permission: bool = True
    priority: int = 100


def _property(name: str, domain: str, categories: tuple[str, ...], priority: int) -> PropertySource:
    return PropertySource(name, domain, "property", categories, priority=priority, source_url=f"https://{domain}")


def _accommodation(name: str, domain: str, category: str, priority: int) -> PropertySource:
    return PropertySource(name, domain, category, (category, "ACCOMMODATION"), priority=priority, source_url=f"https://{domain}")


# These target policies are conservative. They are discoverable through a
# configured web-search provider but are not consent to scrape their pages.
INDIA_SOURCES: tuple[PropertySource, ...] = (
    _property("99acres", "99acres.com", ("PROPERTY_RENT", "PROPERTY_SALE", "PG"), 10),
    _property("MagicBricks", "magicbricks.com", ("PROPERTY_RENT", "PROPERTY_SALE", "PG"), 10),
    _property("Housing.com", "housing.com", ("PROPERTY_RENT", "PROPERTY_SALE"), 10),
    _property("NoBroker", "nobroker.in", ("PROPERTY_RENT", "PROPERTY_SALE", "PG"), 15),
    _property("Square Yards", "squareyards.com", ("PROPERTY_RENT", "PROPERTY_SALE"), 20),
    _property("RealEstateIndia", "realestateindia.com", ("PROPERTY_RENT", "PROPERTY_SALE", "PG"), 30),
    _property("PropTiger", "proptiger.com", ("PROPERTY_SALE",), 25),
    _property("Makaan", "makaan.com", ("PROPERTY_RENT", "PROPERTY_SALE", "PG"), 25),
    _property("OLX", "olx.in", ("PROPERTY_RENT", "PROPERTY_SALE", "PG"), 45),
)

ACCOMMODATION_SOURCES: tuple[PropertySource, ...] = (
    _accommodation("Booking.com", "booking.com", "HOTEL", 10),
    _accommodation("Google Hotels", "google.com", "HOTEL", 15),
    _accommodation("MakeMyTrip", "makemytrip.com", "HOTEL", 15),
    _accommodation("Agoda", "agoda.com", "HOTEL", 20),
    _accommodation("Trivago", "trivago.in", "HOTEL", 25),
    _accommodation("Airbnb", "airbnb.com", "VACATION_RENTAL", 20),
    _accommodation("Vrbo", "vrbo.com", "VACATION_RENTAL", 25),
    _accommodation("cozycozy", "cozycozy.com", "SHORT_STAY", 30),
    _accommodation("Hostelworld", "hostelworld.com", "HOSTEL", 20),
)

SOURCE_REGISTRY: tuple[PropertySource, ...] = INDIA_SOURCES + ACCOMMODATION_SOURCES


def get_sources() -> list[PropertySource]:
    return list(SOURCE_REGISTRY)


def get_source_by_domain(domain: str) -> Optional[PropertySource]:
    domain = (domain or "").lower().lstrip(".").removeprefix("www.")
    for source in SOURCE_REGISTRY:
        if domain == source.domain or domain.endswith("." + source.domain):
            return source
    return None


def select_sources(intent, limit: int = 4) -> list[PropertySource]:
    """Return bounded, category-matched sources with explicit policies."""
    category = getattr(intent, "category", None) or (
        "PROPERTY_RENT" if getattr(intent, "listing_type", "sale") == "rent" else "PROPERTY_SALE"
    )
    candidates = [
        source for source in SOURCE_REGISTRY
        if source.enabled and source.discovery_allowed
        and (category in source.categories or (category == "ACCOMMODATION" and "ACCOMMODATION" in source.categories))
    ]
    candidates.sort(key=lambda source: (source.priority, source.name))
    return candidates[:max(1, int(limit))]


def domain_filter_queries(query: str, sources: list[PropertySource]) -> list[str]:
    return [" ".join(part for part in (query, f"site:{source.domain}") if part) for source in sources]
