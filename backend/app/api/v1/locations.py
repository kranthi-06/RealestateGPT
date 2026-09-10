"""Live location intelligence endpoints backed by a configured provider."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.property import Property
from app.providers.google_maps import GoogleMapsProvider, LocationProviderUnavailable
from app.schemas.maps import LiveNearbyResponse, MapProviderStatus, RouteRequest, RouteResponse

router = APIRouter(prefix="/locations", tags=["Location intelligence"])

@router.get("/status", response_model=MapProviderStatus)
async def location_status():
    configured = settings.MAPS_PROVIDER == "google" and bool(settings.GOOGLE_MAPS_SERVER_KEY)
    return MapProviderStatus(configured=configured, provider="google" if configured else "none",
        message="Google Maps integration is ready." if configured else "Google Maps integration is not configured.")

@router.get("/properties/{property_id}/nearby", response_model=LiveNearbyResponse)
async def nearby(property_id: int, category: str, radius_km: float = 3.0, db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id, Property.is_active == True).first()  # noqa: E712
    if not prop: raise HTTPException(status_code=404, detail="Property not found")
    if prop.latitude is None or prop.longitude is None: raise HTTPException(status_code=422, detail="Property coordinates are unavailable")
    try:
        places = GoogleMapsProvider().nearby(prop.latitude, prop.longitude, category, radius_km)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LocationProviderUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return LiveNearbyResponse(property_id=property_id, category=category, radius_km=radius_km, source="Google Places (New)", places=places)

@router.post("/routes", response_model=RouteResponse)
async def route(data: RouteRequest):
    try:
        return GoogleMapsProvider().route((data.origin_latitude, data.origin_longitude), (data.destination_latitude, data.destination_longitude), data.travel_mode)
    except LocationProviderUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
