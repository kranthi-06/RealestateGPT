"""RealEstateGPT - Pydantic schemas for request/response validation"""

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
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
    currency: str = Field(default="INR", min_length=3, max_length=3)
    property_type: str = Field(..., min_length=1, max_length=50)
    listing_type: str = Field(default="sale", pattern="^(sale|rent)$")
    bedrooms: Optional[int] = Field(None, ge=0, le=20)
    bathrooms: Optional[int] = Field(None, ge=0, le=20)
    balconies: Optional[int] = Field(None, ge=0, le=10)
    area_sqft: Optional[float] = Field(None, gt=0)
    area: Optional[float] = Field(None, gt=0)
    area_unit: Optional[str] = Field(default="sqft", pattern="^(sqft|sqm|acre|hectare)$")
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


class PropertyCreate(PropertyBase):
    """Admin-only property-write contract with explicit provenance."""
    slug: Optional[str] = Field(None, min_length=3, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    source: str = Field(..., min_length=1, max_length=100)
    source_type: str = Field(..., pattern="^(licensed_feed|partner_api|admin|user|demo)$")
    source_id: Optional[str] = Field(None, min_length=1, max_length=255)
    source_url: Optional[str] = Field(None, max_length=2_000)
    verification_status: str = Field(default="unverified", pattern="^(verified|unverified|rejected)$")
    images: List[str] = Field(default_factory=list, max_length=30)
    amenities: List[AmenityResponse] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def coordinates_are_paired(self) -> "PropertyCreate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self

    @field_validator("images")
    @classmethod
    def images_are_urls(cls, values: List[str]) -> List[str]:
        if any(not value.strip().startswith(("https://", "http://")) for value in values):
            raise ValueError("Property images must use an http(s) URL")
        return [value.strip() for value in values]


class PropertyUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=500)
    description: Optional[str] = Field(None, max_length=10_000)
    price: Optional[float] = Field(None, gt=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    property_type: Optional[str] = Field(None, min_length=1, max_length=50)
    listing_type: Optional[str] = Field(None, pattern="^(sale|rent)$")
    bedrooms: Optional[int] = Field(None, ge=0, le=20)
    bathrooms: Optional[int] = Field(None, ge=0, le=20)
    furnishing: Optional[str] = Field(None, max_length=50)
    area: Optional[float] = Field(None, gt=0)
    area_unit: Optional[str] = Field(None, pattern="^(sqft|sqm|acre|hectare)$")
    area_sqft: Optional[float] = Field(None, gt=0)
    amenities: Optional[List[AmenityResponse]] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    locality: Optional[str] = Field(None, max_length=100)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    images: Optional[List[str]] = Field(None, max_length=30)
    source_url: Optional[str] = Field(None, max_length=2_000)
    verification_status: Optional[str] = Field(None, pattern="^(verified|unverified|rejected)$")
    last_verified_at: Optional[datetime] = None

    @field_validator("images")
    @classmethod
    def images_are_urls(cls, values: Optional[List[str]]) -> Optional[List[str]]:
        if values is not None and any(not value.strip().startswith(("https://", "http://")) for value in values):
            raise ValueError("Property images must use an http(s) URL")
        return [value.strip() for value in values] if values is not None else values


class PropertyResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    slug: str
    price: float
    currency: str = "INR"
    price_per_sqft: Optional[float] = None
    maintenance_charge: Optional[float] = None
    property_type: str
    listing_type: str
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    balconies: Optional[int] = None
    area_sqft: Optional[float] = None
    area: Optional[float] = None
    area_unit: Optional[str] = None
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
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    source_type: Optional[str] = None
    last_verified_at: Optional[datetime] = None
    data_quality_score: float = 0.0
    verification_status: str
    is_featured: bool
    is_synthetic: bool
    image_urls: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    amenities: List[AmenityResponse] = Field(default_factory=list)
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
    bathrooms: Optional[int] = Field(None, ge=0)
    min_bedrooms: Optional[int] = Field(None, ge=0)
    max_bedrooms: Optional[int] = Field(None, ge=0)
    min_area: Optional[float] = Field(None, ge=0)
    max_area: Optional[float] = Field(None, ge=0)
    furnishing: Optional[str] = None
    amenities: Optional[List[str]] = Field(None, max_length=20)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_km: Optional[float] = Field(None, gt=0, le=100)
    construction_status: Optional[str] = None
    sort_by: Optional[str] = Field(default="created_at", pattern="^(price|area_sqft|created_at|updated_at|bedrooms|bathrooms|price_per_sqft)$")
    sort_order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=50)

    @model_validator(mode="after")
    def validate_ranges(self) -> "PropertySearchParams":
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price cannot exceed max_price")
        if self.min_area is not None and self.max_area is not None and self.min_area > self.max_area:
            raise ValueError("min_area cannot exceed max_area")
        coordinates = (self.latitude is not None, self.longitude is not None, self.radius_km is not None)
        if any(coordinates) and not all(coordinates):
            raise ValueError("latitude, longitude and radius_km must be provided together")
        return self


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


class PropertyBulkRequest(BaseModel):
    property_ids: List[int] = Field(..., min_length=1, max_length=12)


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
