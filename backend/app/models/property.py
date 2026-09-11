"""RealEstateGPT - Property and Amenity domain models (MongoDB documents).

Properties keep provenance and quality metadata so synthetic/demo listings are
never presented as verified market inventory. Coordinates are stored both as
plain lat/lon fields (API contract) and as a GeoJSON ``location`` field that
powers 2dsphere geospatial queries.
"""

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.user import utcnow


class Amenity(BaseModel):
    id: int = 0
    name: str = Field(min_length=1, max_length=100)
    category: Optional[str] = None
    icon: Optional[str] = None


class Property(BaseModel):
    id: Optional[int] = None
    title: str = Field(min_length=5, max_length=500)
    description: Optional[str] = Field(default=None, max_length=10_000)
    slug: str = Field(min_length=3, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    price: float = Field(gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    price_per_sqft: Optional[float] = None
    maintenance_charge: Optional[float] = None
    property_type: str = Field(min_length=1, max_length=50)
    listing_type: Literal["sale", "rent"] = "sale"
    bedrooms: Optional[int] = Field(default=None, ge=0, le=20)
    bathrooms: Optional[int] = Field(default=None, ge=0, le=20)
    balconies: Optional[int] = None
    # ``area``/``area_unit`` are the canonical feed fields. ``area_sqft`` is
    # retained for the existing UI/API contract and is normalized for sqft.
    area: Optional[float] = Field(default=None, gt=0)
    area_unit: Optional[Literal["sqft", "sqm", "acre", "hectare"]] = "sqft"
    area_sqft: Optional[float] = Field(default=None, gt=0)
    carpet_area_sqft: Optional[float] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    property_age: Optional[int] = None  # years
    facing: Optional[str] = None
    furnishing: Optional[str] = None
    parking: Optional[int] = 0
    construction_status: Optional[str] = None

    # Location
    address: Optional[str] = None
    locality: Optional[str] = None
    city: str = Field(min_length=1, max_length=100)
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    location: Optional[dict] = None  # GeoJSON Point for 2dsphere

    # Builder / project
    builder_name: Optional[str] = None
    project_name: Optional[str] = None

    # Provenance + data quality
    source: str = Field(min_length=1, max_length=100)
    source_type: Literal["licensed_feed", "partner_api", "admin", "user", "demo"]
    source_url: Optional[str] = Field(default=None, max_length=2_000)
    source_id: Optional[str] = Field(default=None, min_length=1, max_length=255)
    last_verified_at: Optional[datetime] = None
    data_quality_score: float = Field(default=0.0, ge=0, le=100)

    # Verification
    verification_status: Literal["verified", "unverified", "rejected"] = "unverified"
    is_featured: bool = False
    is_active: bool = True
    is_synthetic: bool = True  # True for seed/demo data, False for real listings

    # ``images`` is canonical. ``image_urls`` remains a read-compatible
    # projection for the existing frontend during migration.
    images: List[str] = Field(default_factory=list, max_length=30)
    image_urls: Optional[str] = None

    # Timestamps
    listed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    amenities: List[Amenity] = Field(default_factory=list, max_length=100)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("title", "property_type", "city", "source", "locality", "furnishing", mode="before")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = str(value).strip()
        if not value:
            raise ValueError("Text fields cannot be blank")
        return value

    @field_validator("images")
    @classmethod
    def validate_images(cls, values: List[str]) -> List[str]:
        cleaned = []
        for value in values:
            value = value.strip()
            if not value.startswith(("https://", "http://")):
                raise ValueError("Property images must use an http(s) URL")
            cleaned.append(value)
        return cleaned

    @model_validator(mode="after")
    def normalize_geo_and_area(self) -> "Property":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        if self.latitude is not None and self.longitude is not None:
            self.location = {"type": "Point", "coordinates": [self.longitude, self.latitude]}
        if self.area is None and self.area_sqft is not None:
            self.area, self.area_unit = self.area_sqft, "sqft"
        if self.area_sqft is None and self.area is not None and self.area_unit == "sqft":
            self.area_sqft = self.area
        if not self.images and self.image_urls:
            self.images = self.image_url_list
        if self.images:
            self.image_urls = ",".join(self.images)
        if self.source_type == "demo":
            self.is_synthetic = True
            if self.verification_status == "verified":
                raise ValueError("Demo properties cannot be marked verified")
        return self

    @property
    def image_url_list(self) -> List[str]:
        if not self.image_urls:
            return []
        return [url.strip() for url in self.image_urls.split(",") if url.strip()]

    @classmethod
    def from_doc(cls, doc: Optional[dict]) -> Optional["Property"]:
        if not doc:
            return None
        data = dict(doc)
        data["id"] = data.pop("_id")
        return cls(**data)

    def __repr__(self) -> str:
        return f"<Property {self.title} - {self.city}>"
