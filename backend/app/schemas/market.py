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


class MarketSnapshotResponse(BaseModel):
    generated_at: datetime
    source: str
    query: Dict[str, Any]
    localities: List[str] = []
    totals: Dict[str, Any]
    bedroom_breakdown: Dict[str, int] = {}
    apartments: Dict[str, Any]
    houses: Dict[str, Any]
    land: Dict[str, Any]
    rents: Dict[str, Any]
    locality_comparison: List[LocalityComparisonResponse] = []
    price_history: List[PriceHistoryPointResponse] = []
    trend: Dict[str, Any] = {}
    indicators: Dict[str, Any] = {}
    coverage: Dict[str, Any] = {}
    insufficient_data: Optional[Dict[str, str]] = None


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
