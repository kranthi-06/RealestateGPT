"""Market intelligence response schemas.

These are aggregate-only responses: no individual listing rows, so a small
response cannot be used to reverse-engineer private listing data.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PriceStatResponse(BaseModel):
    sample_size: int = 0
    median: Optional[float] = None
    mean: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    is_measured: bool = False


class LocalityComparisonResponse(BaseModel):
    locality: str
    listings: int
    median_price: Optional[float] = None
    avg_price_per_sqft: Optional[float] = None
    measured: bool = False


class PriceHistoryPointResponse(BaseModel):
    month: str
    observations: int
    avg_price: Optional[float] = None
    avg_previous_price: Optional[float] = None


class PriceDistributionBucketResponse(BaseModel):
    """One histogram bucket of observed asking prices.

    ``from``/``to`` come straight from the service; the aliases keep the JSON
    keys readable while ``from_value``/``to_value`` avoid shadowing a builtin
    inside Python.
    """

    model_config = {"populate_by_name": True}

    label: str = ""
    from_value: Optional[float] = Field(default=None, alias="from")
    to_value: Optional[float] = Field(default=None, alias="to")
    count: int = 0


class PriceStatGroup(BaseModel):
    """A price stat plus its price-per-square-foot counterpart."""

    prices: PriceStatResponse = Field(default_factory=PriceStatResponse)
    price_per_sqft: PriceStatResponse = Field(default_factory=PriceStatResponse)


class LandStatGroup(PriceStatGroup):
    """A land group also reports price per square yard."""

    price_per_sq_yard: PriceStatResponse = Field(default_factory=PriceStatResponse)


class RentStatGroup(BaseModel):
    monthly: PriceStatResponse = Field(default_factory=PriceStatResponse)
    price_per_sqft_monthly: PriceStatResponse = Field(default_factory=PriceStatResponse)


class MarketSnapshotResponse(BaseModel):
    generated_at: datetime
    source: str
    query: Dict[str, Any]
    localities: List[str] = []
    totals: Dict[str, Any]
    bedroom_breakdown: Dict[str, int] = {}
    apartments: PriceStatGroup = Field(default_factory=PriceStatGroup)
    houses: PriceStatGroup = Field(default_factory=PriceStatGroup)
    land: LandStatGroup = Field(default_factory=LandStatGroup)
    rents: RentStatGroup = Field(default_factory=RentStatGroup)
    locality_comparison: List[LocalityComparisonResponse] = []
    price_history: List[PriceHistoryPointResponse] = []
    price_distribution: List[PriceDistributionBucketResponse] = []
    trend: Dict[str, Any] = {}
    indicators: Dict[str, Any] = {}
    coverage: Dict[str, Any] = {}
    insufficient_data: Optional[Dict[str, str]] = None
    # ── External market intelligence (a separate, clearly identified source) ──
    external: Optional[Dict[str, Any]] = None


class ExternalMarketRequest(BaseModel):
    """External market research request. Never touches the catalogue."""

    location: str = Field(..., min_length=1, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    locality: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    listing_type: Optional[str] = Field(None, pattern="^(sale|rent)$")
    property_type: Optional[str] = Field(None, max_length=50)
    bedrooms: Optional[int] = Field(None, ge=0, le=20)
    currency: str = Field("INR", max_length=3)
    language: str = Field("en", max_length=5)


class ExternalMarketResponse(BaseModel):
    status: str                       # ok | no_results | unavailable | not_configured
    message: Optional[str] = None
    location_input: str
    resolved: Dict[str, Any] = {}
    sources: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []
    statistics: Dict[str, Any] = {}
    ai_summary: Optional[Dict[str, Any]] = None
    queries_used: List[str] = []
    provider: Optional[str] = None
    cache: Dict[str, Any] = {}
    generated_at: str
    data_class: str = "external_observation"
    disclaimer: str = (
        "External observations were retrieved from third-party web sources. They are "
        "asking prices and published estimates, not verified listings, and are not "
        "guaranteed or exact market rates. Nothing here is estimated by RealEstateGPT."
    )


class CityTotalResponse(BaseModel):
    city: str
    listings: int
    sale: int
    rent: int
    median_price: Optional[float] = None
    locality_count: int = 0


class MarketInsightResponse(BaseModel):
    generated_at: datetime
    cities: List[CityTotalResponse] = []
    minimum_sample: int = Field(3)
    note: str
