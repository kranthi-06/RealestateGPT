"""RealEstateGPT - Pydantic schemas for request/response validation"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime
import re


# ─── Auth Schemas ────────────────────────────────────────

class UserRegister(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    full_name: str = Field(..., min_length=2, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    phone: Optional[str] = Field(None, max_length=20)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v):
            raise ValueError("Invalid email address")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        return v


class UserLogin(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v):
        return v.lower().strip()


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    preferred_cities: Optional[str] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    preferred_cities: Optional[str] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ─── Property Schemas ────────────────────────────────────

class AmenityResponse(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    icon: Optional[str] = None

    model_config = {"from_attributes": True}


class PropertyBase(BaseModel):
    title: str = Field(..., min_length=5, max_length=500)
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    property_type: str = Field(..., min_length=1, max_length=50)
    listing_type: str = Field(default="sale", pattern="^(sale|rent)$")
    bedrooms: Optional[int] = Field(None, ge=0, le=20)
    bathrooms: Optional[int] = Field(None, ge=0, le=20)
    balconies: Optional[int] = Field(None, ge=0, le=10)
    area_sqft: Optional[float] = Field(None, gt=0)
    carpet_area_sqft: Optional[float] = Field(None, gt=0)
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    property_age: Optional[int] = Field(None, ge=0)
    facing: Optional[str] = None
    furnishing: Optional[str] = None
    parking: Optional[int] = Field(None, ge=0)
    construction_status: Optional[str] = None
    address: Optional[str] = None
    locality: Optional[str] = None
    city: str = Field(..., min_length=1, max_length=100)
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    builder_name: Optional[str] = None
    project_name: Optional[str] = None


class PropertyResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    slug: str
    price: float
    price_per_sqft: Optional[float] = None
    maintenance_charge: Optional[float] = None
    property_type: str
    listing_type: str
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    balconies: Optional[int] = None
    area_sqft: Optional[float] = None
    carpet_area_sqft: Optional[float] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    property_age: Optional[int] = None
    facing: Optional[str] = None
    furnishing: Optional[str] = None
    parking: Optional[int] = None
    construction_status: Optional[str] = None
    address: Optional[str] = None
    locality: Optional[str] = None
    city: str
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    builder_name: Optional[str] = None
    project_name: Optional[str] = None
    source: Optional[str] = None
    verification_status: str
    is_featured: bool
    is_synthetic: bool
    image_urls: Optional[str] = None
    amenities: List[AmenityResponse] = []
    listed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    is_saved: Optional[bool] = None  # Populated per-user

    model_config = {"from_attributes": True}


class PropertyListResponse(BaseModel):
    properties: List[PropertyResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PropertyCardResponse(BaseModel):
    """Lighter schema for property cards in listings."""
    id: int
    title: str
    slug: str
    price: float
    price_per_sqft: Optional[float] = None
    property_type: str
    listing_type: str
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area_sqft: Optional[float] = None
    furnishing: Optional[str] = None
    locality: Optional[str] = None
    city: str
    builder_name: Optional[str] = None
    verification_status: str
    is_featured: bool
    is_synthetic: bool
    image_urls: Optional[str] = None
    amenities: List[AmenityResponse] = []
    created_at: datetime
    is_saved: Optional[bool] = None

    model_config = {"from_attributes": True}


# ─── Search Schemas ──────────────────────────────────────

class PropertySearchParams(BaseModel):
    q: Optional[str] = None  # text search query
    city: Optional[str] = None
    locality: Optional[str] = None
    property_type: Optional[str] = None
    listing_type: Optional[str] = Field(None, pattern="^(sale|rent)$")
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    bedrooms: Optional[int] = Field(None, ge=0)
    min_bedrooms: Optional[int] = Field(None, ge=0)
    max_bedrooms: Optional[int] = Field(None, ge=0)
    min_area: Optional[float] = Field(None, ge=0)
    max_area: Optional[float] = Field(None, ge=0)
    furnishing: Optional[str] = None
    construction_status: Optional[str] = None
    sort_by: Optional[str] = Field(default="created_at", pattern="^(price|area_sqft|created_at|bedrooms|price_per_sqft)$")
    sort_order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=50)


# ─── Saved Schemas ───────────────────────────────────────

class SavePropertyRequest(BaseModel):
    property_id: int
    notes: Optional[str] = None


class SavedPropertyResponse(BaseModel):
    id: int
    property_id: int
    notes: Optional[str] = None
    created_at: datetime
    property: PropertyCardResponse

    model_config = {"from_attributes": True}


class SaveSearchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
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


class SavedSearchResponse(BaseModel):
    id: int
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
    notify_enabled: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Comparison Schemas ──────────────────────────────────

class ComparisonCreateRequest(BaseModel):
    name: Optional[str] = None
    property_ids: List[int] = Field(..., min_length=2, max_length=4)


class ComparisonResponse(BaseModel):
    id: int
    name: Optional[str] = None
    property_ids: str
    created_at: datetime
    properties: List[PropertyResponse] = []

    model_config = {"from_attributes": True}


# ─── Admin Schemas ───────────────────────────────────────

class AdminStatsResponse(BaseModel):
    total_properties: int
    active_properties: int
    verified_properties: int
    total_users: int
    total_saved_properties: int
    total_saved_searches: int
    total_comparisons: int
    total_searches: int
    total_ai_messages: int = 0
    total_documents: int = 0
    total_recommendations: int = 0
    properties_by_city: dict
    properties_by_type: dict


# ─── Re-exports for AI / Finance / Location / Documents modules ────────

from app.schemas.ai import (  # noqa: E402
    NearbyRequirement,
    ParsedQuery,
    ScoreComponent,
    ScoredProperty,
    AiSearchRequest,
    AiSearchResponse,
    Citation,
    AssistantRequest,
    ToolCallRecord,
    AssistantResponse,
    ConversationSummary,
    MessageResponse,
)
from app.schemas.finance import (  # noqa: E402
    EmiRequest,
    EmiResponse,
    AffordabilityRequest,
    AffordabilityResponse,
    RentalYieldRequest,
    RentalYieldResponse,
    RoiRequest,
    RoiResponse,
    YearProjection,
    PriceEstimateResponse,
    PriceFairnessResponse,
)
from app.schemas.location import (  # noqa: E402
    NearbyPlaceResponse,
    NearbyPlacesResponse,
    CategorySummary,
    PropertyLocationContextResponse,
    DistanceRequest,
    DistanceResponse,
)
from app.schemas.documents_admin import (  # noqa: E402
    DocumentResponse,
    DocumentUploadResponse,
    DocumentAskResponse,
    AdminUserResponse,
    AdminUserListResponse,
    AdminPropertyItemResponse,
    AdminPropertyListResponse,
    AuditLogResponse,
    AdminAiUsageResponse,
)
