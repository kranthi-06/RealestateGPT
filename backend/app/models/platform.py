"""RealEstateGPT - Platform domain models (MongoDB documents).

Audit, AI conversations/messages, recommendations, price predictions,
documents/chunks, notifications, property verification and nearby places.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.user import utcnow


class MongoModel(BaseModel):
    """Base class providing Mongo ``_id`` -> domain ``id`` conversion."""

    @classmethod
    def from_doc(cls, doc: Optional[dict]):
        if not doc:
            return None
        data = dict(doc)
        data["id"] = data.pop("_id")
        return cls(**data)


# ─── Audit ──────────────────────────────────────────────────────────────

class AuditLog(MongoModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    action: str
    entity: Optional[str] = None
    entity_id: Optional[int] = None
    detail: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


# ─── AI conversations ──────────────────────────────────────────────────

class Conversation(MongoModel):
    id: Optional[int] = None
    user_id: int
    title: Optional[str] = None
    property_id: Optional[int] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    messages: List["Message"] = []


class Message(MongoModel):
    id: Optional[int] = None
    conversation_id: int
    role: str  # user | assistant | system
    content: str
    meta_json: Optional[dict] = None  # tool_calls, citations, parsed query, scores
    created_at: datetime = Field(default_factory=utcnow)


class Recommendation(MongoModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    conversation_id: Optional[int] = None
    property_id: int
    overall_score: float
    component_scores: Optional[dict] = None
    factors: Optional[dict] = None  # {positive: [...], negative: [...]}
    created_at: datetime = Field(default_factory=utcnow)


# ─── ML price estimation ───────────────────────────────────────────────

class PricePrediction(MongoModel):
    id: Optional[int] = None
    property_id: int
    predicted_price: Optional[float] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    model_version: Optional[str] = None
    inputs: Optional[dict] = None
    created_at: datetime = Field(default_factory=utcnow)


# ─── Documents ─────────────────────────────────────────────────────────

class Document(MongoModel):
    id: Optional[int] = None
    user_id: int
    property_id: Optional[int] = None
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    storage_key: Optional[str] = None
    status: str = "uploaded"  # uploaded | processing | ready | failed
    text_preview: Optional[str] = None
    extraction_error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class DocumentChunk(MongoModel):
    id: Optional[int] = None
    document_id: int
    chunk_index: int
    content: str
    page_number: Optional[int] = None
    embedding: Optional[list] = None
    metadata_json: Optional[dict] = None
    created_at: datetime = Field(default_factory=utcnow)


# ─── Notifications ─────────────────────────────────────────────────────

class Notification(MongoModel):
    id: Optional[int] = None
    user_id: int
    type: str  # save_alert | system | ...
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    is_read: bool = False
    created_at: datetime = Field(default_factory=utcnow)


# ─── Property verification ─────────────────────────────────────────────

class PropertyVerification(MongoModel):
    id: Optional[int] = None
    property_id: int
    admin_id: Optional[int] = None
    status: str  # verified | unverified | rejected
    note: Optional[str] = None
    explanation: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


# ─── Location intelligence ─────────────────────────────────────────────

class NearbyPlace(MongoModel):
    id: Optional[int] = None
    name: str
    place_type: str  # metro | hospital | school | ...
    category: Optional[str] = None  # healthcare | transport | ...
    locality: Optional[str] = None
    city: Optional[str] = None
    latitude: float
    longitude: float
    location: Optional[dict] = None  # GeoJSON Point for 2dsphere
    source: Optional[str] = "seed_data"
    is_synthetic: bool = True
    created_at: datetime = Field(default_factory=utcnow)