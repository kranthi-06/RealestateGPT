"""RealEstateGPT - Saved properties, saved searches, comparisons, search history
domain models (MongoDB documents)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.property import Property
from app.models.user import utcnow


class SavedProperty(BaseModel):
    id: Optional[int] = None
    user_id: int
    property_id: int
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    property: Optional[Property] = None  # populated by the repository when needed

    @classmethod
    def from_doc(cls, doc: Optional[dict]) -> Optional["SavedProperty"]:
        if not doc:
            return None
        data = dict(doc)
        data["id"] = data.pop("_id")
        return cls(**data)


class SavedSearch(BaseModel):
    id: Optional[int] = None
    user_id: int
    name: str
    city: Optional[str] = None
    locality: Optional[str] = None
    property_type: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    bedrooms: Optional[int] = None
    min_area: Optional[float] = None
    max_area: Optional[float] = None
    furnishing: Optional[str] = None
    query_text: Optional[str] = None
    notify_enabled: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @classmethod
    def from_doc(cls, doc: Optional[dict]) -> Optional["SavedSearch"]:
        if not doc:
            return None
        data = dict(doc)
        data["id"] = data.pop("_id")
        return cls(**data)


class Comparison(BaseModel):
    id: Optional[int] = None
    user_id: int
    name: Optional[str] = None
    property_ids: str = ""  # comma-separated property IDs (API contract)
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def property_id_list(self) -> List[int]:
        return [int(pid.strip()) for pid in self.property_ids.split(",") if pid.strip()]

    @classmethod
    def from_doc(cls, doc: Optional[dict]) -> Optional["Comparison"]:
        if not doc:
            return None
        data = dict(doc)
        data["id"] = data.pop("_id")
        return cls(**data)


class SearchHistory(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    query_text: Optional[str] = None
    filters_json: Optional[str] = None  # JSON string of applied filters
    result_count: Optional[int] = None
    created_at: datetime = Field(default_factory=utcnow)

    @classmethod
    def from_doc(cls, doc: Optional[dict]) -> Optional["SearchHistory"]:
        if not doc:
            return None
        data = dict(doc)
        data["id"] = data.pop("_id")
        return cls(**data)