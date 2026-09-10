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
    maps_url: Optional[str] = None
    photo_resource: Optional[str] = None
    attributions: list[str] = []

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
