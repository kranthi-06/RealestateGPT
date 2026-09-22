"""Property source registry + source router for web discovery.

The registry describes *configuration*, never permission-to-scrape. Every source
carries capability metadata (``discovery_allowed`` = a search provider may
legitimately return its pages; ``page_fetch_allowed`` = we may fetch its pages;
``requires_permission``). These values must be set by an operator — the
application never assumes a source permits automated access.

The router picks a *bounded* set of sources for a SearchIntent so discovery
never attempts to crawl the entire internet.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PropertySource:
    name: str
    domain: str
    country: str = "IN"
    categories: tuple[str, ...] = ("rent", "sale")
    enabled: bool = True
    discovery_allowed: bool = True
    page_fetch_allowed: bool = False
    requires_permission: bool = True
    priority: int = 100


#: India property-source registry (configuration, not entitlements).
INDIA_SOURCES: tuple[PropertySource, ...] = (
    PropertySource("99acres", "99acres.com", categories=("rent", "sale", "pg", "commercial", "projects"), priority=10),
    PropertySource("MagicBricks", "magicbricks.com", categories=("rent", "sale", "pg", "commercial", "projects"), priority=10),
    PropertySource("Housing.com", "housing.com", categories=("rent", "sale", "commercial", "projects"), priority=10),
    PropertySource("NoBroker", "nobroker.in", categories=("rent", "sale", "pg"), priority=15),
    PropertySource("Square Yards", "squareyards.com", categories=("rent", "sale", "commercial", "projects"), priority=20),
    PropertySource("RealEstateIndia", "realestateindia.com", categories=("rent", "sale", "pg"), priority=30),
    PropertySource("PropTiger", "proptiger.com", categories=("sale", "commercial", "projects"), priority=25),
    PropertySource("Makaan", "makaan.com", categories=("rent", "sale", "pg"), priority=25),
    PropertySource("CommonFloor", "commonfloor.com", categories=("rent", "sale", "pg"), priority=30),
    PropertySource("PropertyWala", "propertywala.com", categories=("rent", "sale"), priority=40),
    PropertySource("Sulekha", "sulekha.com", categories=("sale", "pg"), priority=40),
    PropertySource("OLX", "olx.in", categories=("rent", "sale", "pg"), priority=45, page_fetch_allowed=False),
)


def get_sources() -> list[PropertySource]:
    """All registered sources (statically provided; replaceable by config later)."""
    return list(INDIA_SOURCES)


def get_source_by_domain(domain: str) -> Optional[PropertySource]:
    """Look up a source by its domain (best effort, subdomains included)."""
    domain = (domain or "").lower().lstrip(".")
    for source in INDIA_SOURCES:
        if domain == source.domain or domain.endswith("." + source.domain):
            return source
    return None


def select_sources(intent, limit: int = 4) -> list[PropertySource]:
    """Route a SearchIntent to a bounded, priority-ordered source list.

    ``limit`` is the maximum number of sources to include (bounded cost).
    """
    listing_type = (getattr(intent, "listing_type", None) or "sale").lower()
    property_type = getattr(intent, "property_type", None) or ""
    transaction = "rent" if listing_type == "rent" else "sale"

    candidates: list[PropertySource] = []
    for source in INDIA_SOURCES:
        if not source.enabled or not source.discovery_allowed:
            continue
        categories = set(source.categories)
        if transaction not in categories:
            # Projects/pg sources still matter for non-residential angles.
            if transaction == "sale" and "projects" in categories:
                pass
            elif property_type in ("pg", "commercial", "plot", "plot_and_land") and property_type in categories:
                pass
            else:
                continue
        candidates.append(source)

    # Deterministic priority order (then name) so tests and production agree.
    candidates.sort(key=lambda s: (s.priority, s.name))
    return candidates[: max(1, int(limit))]


def domain_filter_queries(query: str, sources: list[PropertySource]) -> list[str]:
    """Return per-source ``site:``-augmented queries when supported.

    The actual provider decides whether ``site:`` filtering is honored; we only
    build the bounded query set. When ``WEB_SEARCH_ALLOWED_DOMAINS`` is set the
    discovery service applies a strict post-filter instead.
    """
    return [" ".join(part for part in (query, f"site:{s.domain}") if part) for s in sources]