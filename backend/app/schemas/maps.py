from pydantic import BaseModel, Field
from typing import Optional

class MapProviderStatus(BaseModel):
    configured: bool
    provider: str
    message: str

class LivePlace(BaseModel):
    provider: str
    place_id: Optional[str] = None
    name: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    maps_url: Optional[str] = None
    photo_resource: Optional[str] = None
    attributions: list[str] = []
    distance_km: Optional[float] = None
    travel_minutes: Optional[float] = None
    travel_mode: Optional[str] = None
    photo_url: Optional[str] = None
    website_url: Optional[str] = None
    phone_number: Optional[str] = None
    opening_hours: list[str] = []

class LiveNearbyResponse(BaseModel):
    property_id: int
    category: str
    radius_km: float
    source: str
    places: list[LivePlace]

class RouteRequest(BaseModel):
    origin_latitude: float = Field(ge=-90, le=90)
    origin_longitude: float = Field(ge=-180, le=180)
    destination_latitude: float = Field(ge=-90, le=90)
    destination_longitude: float = Field(ge=-180, le=180)
    travel_mode: str = Field(default="DRIVE", pattern="^(DRIVE|WALK|BICYCLE|TRANSIT)$")

class RouteResponse(BaseModel):
    distance_km: float
    duration_minutes: float
    mode: str
    provider: str


class GeocodeRequest(BaseModel):
    address: str = Field(min_length=3, max_length=500)


class GeocodeResponse(BaseModel):
    formatted_address: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    place_id: Optional[str] = None
    provider: str
