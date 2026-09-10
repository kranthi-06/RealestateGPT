"""RealEstateGPT - Property and related models"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, Table, func
)
from sqlalchemy.orm import relationship
from app.core.database import Base


# Many-to-many association table for property amenities
property_amenities = Table(
    "property_amenities",
    Base.metadata,
    Column("property_id", Integer, ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id", Integer, ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
)


class Amenity(Base):
    __tablename__ = "amenities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(50), nullable=True)  # safety, lifestyle, convenience, etc.
    icon = Column(String(50), nullable=True)

    properties = relationship("Property", secondary=property_amenities, back_populates="amenities")

    def __repr__(self):
        return f"<Amenity {self.name}>"


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    slug = Column(String(500), unique=True, index=True, nullable=False)

    # Pricing
    price = Column(Float, nullable=False, index=True)
    price_per_sqft = Column(Float, nullable=True)
    maintenance_charge = Column(Float, nullable=True)

    # Property details
    property_type = Column(String(50), nullable=False, index=True)  # apartment, villa, plot, etc.
    listing_type = Column(String(20), nullable=False, default="sale", index=True)  # sale, rent
    bedrooms = Column(Integer, nullable=True, index=True)
    bathrooms = Column(Integer, nullable=True)
    balconies = Column(Integer, nullable=True)
    area_sqft = Column(Float, nullable=True, index=True)
    carpet_area_sqft = Column(Float, nullable=True)
    floor = Column(Integer, nullable=True)
    total_floors = Column(Integer, nullable=True)
    property_age = Column(Integer, nullable=True)  # years
    facing = Column(String(20), nullable=True)
    furnishing = Column(String(30), nullable=True, index=True)  # furnished, semi-furnished, unfurnished
    parking = Column(Integer, nullable=True, default=0)
    construction_status = Column(String(30), nullable=True)  # ready, under_construction

    # Location
    address = Column(String(500), nullable=True)
    locality = Column(String(200), nullable=True, index=True)
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Builder/Developer
    builder_name = Column(String(200), nullable=True)
    project_name = Column(String(200), nullable=True)

    # Source/Provenance
    source = Column(String(100), nullable=True, default="seed_data")
    source_url = Column(String(1000), nullable=True)
    source_id = Column(String(200), nullable=True)

    # Verification
    verification_status = Column(String(30), nullable=False, default="unverified", index=True)
    is_featured = Column(Boolean, default=False, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_synthetic = Column(Boolean, default=True, nullable=False)  # True for seed/demo data

    # Images (stored as comma-separated URLs for Phase 1; move to separate table later)
    image_urls = Column(Text, nullable=True)

    # Timestamps
    listed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    amenities = relationship("Amenity", secondary=property_amenities, back_populates="properties")
    saved_by = relationship("SavedProperty", back_populates="property", cascade="all, delete-orphan")

    @property
    def image_url_list(self):
        if not self.image_urls:
            return []
        return [url.strip() for url in self.image_urls.split(",") if url.strip()]

    def __repr__(self):
        return f"<Property {self.title} - {self.city}>"
