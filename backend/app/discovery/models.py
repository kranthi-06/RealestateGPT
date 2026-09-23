"""Core domain models for web property discovery.

``PropertyCandidate`` is the internal, normalized shape produced by
:mod:`app.discovery.extractor` from a :class:`WebSearchResult`. Missing fields
stay ``None`` — never placeholder/fake values.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PropertyCandidate(BaseModel):
    """A property listing hypothesis extracted from a web search result.

    Only fields reasonably supported by the result metadata/snippet/schema are
    populated; everything else remains ``None``. ``confidence`` reflects how
    strongly the source metadata supported the extraction (0..1).
    """

    title: str = Field(..., min_length=1, max_length=500)
    url: str = Field(..., max_length=2048)
    source_domain: str = ""
    source_name: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=4000)
    price: Optional[float] = Field(default=None, ge=0)
    currency: str = "INR"
    transaction_type: Optional[str] = None       # rent | sale
    property_type: Optional[str] = None           # apartment | villa | ...
    category: str = "PROPERTY_SALE"
    provenance: str = "WEB_DISCOVERY"
    bedrooms: Optional[int] = Field(default=None, ge=0, le=20)
    bathrooms: Optional[int] = Field(default=None, ge=0, le=20)
    area: Optional[float] = Field(default=None, ge=0)
    area_unit: Optional[str] = None               # sqft | sqm
    area_sqft: Optional[float] = Field(default=None, ge=0)
    location_text: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = None
    locality: Optional[str] = None
    furnishing: Optional[str] = None              # furnished | semi-furnished | unfurnished
    parking: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    availability: Optional[str] = None
    price_period: Optional[str] = None            # month | night | total | unknown
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    review_count: Optional[int] = Field(default=None, ge=0)
    guests: Optional[int] = Field(default=None, ge=1, le=30)
    amenities: list[str] = Field(default_factory=list)
    image_url: Optional[str] = Field(default=None, max_length=2048)
    source_listing_id: Optional[str] = None
    page_age: Optional[str] = Field(default=None, max_length=100)
    page_fetched: Optional[datetime] = None
    discovered_at: datetime = Field(default_factory=_utcnow)
    confidence: float = Field(default=0.0, ge=0, le=1)
    extraction_method: str = "snippet"            # snippet | schema | metadata | mixed
    provider: str = "web"
    query: Optional[str] = None
    query_hash: Optional[str] = None
