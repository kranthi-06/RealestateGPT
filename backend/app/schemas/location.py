"""RealEstateGPT - Location & map schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List


class NearbyPlaceResponse(BaseModel):
    id: int
    name: str
    place_type: str
    category: Optional[str] = None
    locality: Optional[str] = None
    city: str
    distance_km: Optional[float] = None
    estimated_drive_min: Optional[float] = None

    model_config = {"from_attributes": True}


class NearbyPlacesResponse(BaseModel):
    property_id: int
    place_type: str
    radius_km: float
    count: int
    places: List[NearbyPlaceResponse] = []


class CategorySummary(BaseModel):
    place_type: str
    count: int
    nearest_name: Optional[str] = None
    nearest_distance_km: Optional[float] = None
    within_radius_count: int = 0


class PropertyLocationContextResponse(BaseModel):
    property_id: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: str
    locality: Optional[str] = None
    categories: List[CategorySummary] = []
    all_places: List[NearbyPlaceResponse] = []


class DistanceRequest(BaseModel):
    from_lat: float = Field(ge=-90, le=90)
    from_lon: float = Field(ge=-180, le=180)
    to_lat: float = Field(ge=-90, le=90)
    to_lon: float = Field(ge=-180, le=180)


class DistanceResponse(BaseModel):
    distance_km: float
    formula: str = "haversine"