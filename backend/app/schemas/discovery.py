"""Web property discovery - API request/response schemas.

The unified search response keeps verified inventory and web discoveries in
separate lists so the UI can always distinguish them. Web discovery fields are
minimal and honest — price/bedrooms/area are null when the source did not
provide them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class UnifiedSearchRequest(BaseModel):
    """POST /api/v1/search body."""

    query: str = Field(..., min_length=1, max_length=1000)
    location: Optional[dict[str, Any]] = Field(default=None, description="latitude/longitude/radius_km from browser permission")
    filters: dict[str, Any] = Field(default_factory=dict)
    include_web: bool = True
    limit: int = Field(12, ge=1, le=40)


class WebDiscoveryCard(BaseModel):
    """A web-discovered listing rendered as a premium card.

    ``freshness_label`` is derived from real timestamps, never fabricated:
    \"Discovered moments ago\", \"Found N min ago\", \"Source page date
    unavailable\".
    """

    id: str
    title: str
    url: str
    source_domain: str
    source_name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: str = "INR"
    transaction_type: Optional[str] = None
    category: str = "PROPERTY_SALE"
    provenance: str = "WEB_DISCOVERY"
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area: Optional[float] = None
    area_unit: Optional[str] = None
    area_sqft: Optional[float] = None
    location_text: Optional[str] = None
    city: Optional[str] = None
    locality: Optional[str] = None
    furnishing: Optional[str] = None
    price_period: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    guests: Optional[int] = None
    amenities: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    confidence: float = 0.0
    extraction_method: str = "snippet"
    provider: str = "web"
    discovered_at: datetime
    page_fetched_at: Optional[datetime] = None
    page_age: Optional[str] = None
    freshness_label: str = "Source page date unavailable"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rank_score: Optional[float] = None
    saved: bool = False
    verification_status: str = "web_discovery"


class WebDiscoveryDetail(WebDiscoveryCard):
    """Full discovery record for /discoveries/[id]."""

    query: Optional[str] = None
    query_hash: Optional[str] = None
    raw_metadata_summary: Optional[dict[str, Any]] = None
    source_listing_id: Optional[str] = None


class WebDiscoveryListResponse(BaseModel):
    discoveries: list[WebDiscoveryCard] = Field(default_factory=list)
    total: int = 0


class WebDiscoverySaveResponse(BaseModel):
    discovery_id: str
    saved: bool
    message: str


class SearchMetadata(BaseModel):
    """Unified search response metadata."""

    web_search_used: bool = False
    provider: Optional[str] = None
    provider_status: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    cache_hit: bool = False
    stale_cache_used: bool = False
    queries_used: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    web_message: Optional[str] = None
    latency_ms: dict[str, float] = Field(default_factory=dict)


class UnifiedSearchResponse(BaseModel):
    """Unified verified + web discovery search response."""

    query: str
    parsed: Optional[dict[str, Any]] = None
    verified_properties: list[Any] = Field(default_factory=list)
    verified_total: int = 0
    web_discoveries: list[WebDiscoveryCard] = Field(default_factory=list)
    web_total: int = 0
    sections: list[dict[str, Any]] = Field(default_factory=list)
    facets: dict[str, Any] = Field(default_factory=dict)
    metadata: SearchMetadata = Field(default_factory=SearchMetadata)
