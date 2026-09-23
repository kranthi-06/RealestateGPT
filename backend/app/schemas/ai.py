"""RealEstateGPT - AI schemas: parsed queries, scoring, assistant."""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime


class NearbyRequirement(BaseModel):
    """A proximity requirement such as 'within 2 km of metro'."""
    type: str  # metro, hospital, school, supermarket, it_park, mall, airport...
    max_distance_km: float = Field(gt=0, le=50)
    name_exact: Optional[str] = None  # matches a specific place name when certain


class ParsedQuery(BaseModel):
    """Validated structured extraction from a natural-language query."""
    raw_text: str
    city: Optional[str] = None
    locality: Optional[str] = None
    property_type: Optional[str] = None
    # Inventory category is intentionally separate from property_type. It
    # routes a search to the correct discovery policies without pretending a
    # hotel is an apartment or a web result is verified inventory.
    category: str = "PROPERTY_SALE"
    listing_type: str = "sale"
    bedrooms: Optional[int] = Field(None, ge=0, le=20)
    bathrooms: Optional[int] = Field(None, ge=0, le=20)
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    min_area: Optional[float] = Field(None, ge=0)
    max_area: Optional[float] = Field(None, ge=0)
    furnishing: Optional[str] = None
    amenities: List[str] = Field(default_factory=list, max_length=20)
    nearby_requirements: List[NearbyRequirement] = []
    transport_requirement: Optional[str] = None
    commute_destination: Optional[str] = Field(default=None, max_length=500)
    commute_max_minutes: Optional[int] = Field(default=None, gt=0, le=240)
    lifestyle: List[str] = []  # family, student, investor, pet_friendly, senior...
    guests: Optional[int] = Field(None, ge=1, le=30)
    rooms: Optional[int] = Field(None, ge=1, le=20)
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    breakfast_required: Optional[bool] = None
    cancellation_required: Optional[bool] = None
    intent: str = "home_purchase"  # home_purchase | rental | investment | unknown
    keywords: List[str] = []  # salient tokens for semantic search

    @model_validator(mode="after")
    def validate_price_range(self) -> "ParsedQuery":
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price cannot exceed max_price")
        return self


class SearchIntent(ParsedQuery):
    """Typed, validated intent used by the discovery pipeline.

    This object carries declarative filters only. It is never interpreted as a
    MongoDB query and cannot contain MongoDB operators.
    """


class ScoreComponent(BaseModel):
    key: str
    label: str
    score: float = Field(ge=0)
    max_score: float = Field(ge=0)
    detail: Optional[str] = None


class ScoredProperty(BaseModel):
    property_id: int
    title: str
    slug: str
    price: float
    locality: Optional[str] = None
    city: str
    property_type: str
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area_sqft: Optional[float] = None
    price_per_sqft: Optional[float] = None
    is_featured: bool
    is_synthetic: bool
    verification_status: str
    image_urls: Optional[str] = None
    overall_score: float  # 0-100
    component_scores: List[ScoreComponent] = []
    explanation: Optional[str] = None
    positive_factors: List[str] = []
    negative_factors: List[str] = []
    semantic_similarity: Optional[float] = None
    est_price: Optional[float] = None


class AiSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    intent: Optional[str] = None
    user_filters: dict = {}
    limit: int = Field(12, ge=1, le=40)
    include_scores: bool = True


class AiSearchResponse(BaseModel):
    query: str
    parsed: ParsedQuery
    hard_filtered_count: int
    total: int
    results: List[ScoredProperty] = []
    exceeded: bool = False  # when available candidates < limit
    warning: Optional[str] = None
    metrics: dict = Field(default_factory=dict)


# ─── Assistant ────────────────────────────────────────────────────────

class Citation(BaseModel):
    source_type: str  # property | document | place
    source_id: Optional[int] = None
    label: str
    url: Optional[str] = None


class AssistantRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[int] = None
    property_id: Optional[int] = None      # contextual: "is this worth buying?"
    compare_ids: Optional[List[int]] = None  # contextual: "which is best?"
    limit: int = Field(8, ge=1, le=20)


class ToolCallRecord(BaseModel):
    tool: str
    input: dict = {}
    output_summary: str = ""


class AssistantResponse(BaseModel):
    conversation_id: int
    answer: str
    citations: List[Citation] = []
    tool_calls: List[ToolCallRecord] = []
    parsed_query: Optional[ParsedQuery] = None
    results: List[ScoredProperty] = []
    provider: str  # groq
    warnings: List[str] = []


class ConversationSummary(BaseModel):
    id: int
    title: Optional[str] = None
    property_id: Optional[int] = None
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    meta_json: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}
