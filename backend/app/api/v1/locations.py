"""Configured-provider location intelligence endpoints.

Production uses ``LOCATION_PROVIDER=osm``. Requests are dispatched to exactly
one provider; failures are surfaced as typed HTTP errors and never fall back to
Google, seeded nearby-place records, or invented route data.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.core.config import settings
from app.core.database import get_db
from app.providers.location import (
    LocationProviderInvalidRequest,
    LocationProviderRateLimited,
    LocationProviderUnavailable,
    get_location_provider,
)
from app.repositories.property_repo import PropertyRepository
from app.schemas.maps import (
    GeocodeRequest, GeocodeResponse, LiveNearbyResponse, LivePlace,
    MapProviderStatus, RouteRequest, RouteResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/locations", tags=["Location intelligence"])
_CATEGORIES = "^(metro|hospital|school|college|supermarket|mall|park|it_park)$"


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LocationProviderRateLimited):
        return HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "60"})
    if isinstance(exc, LocationProviderInvalidRequest):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


def _provider():
    return get_location_provider()


def _to_live_place(payload: dict, request: Request) -> LivePlace:
    """Add a server-only Google photo URL only when Google is selected."""
    photo_resource = payload.get("photo_resource")
    if photo_resource and settings.LOCATION_PROVIDER.lower() == "google":
        payload = dict(payload)
        payload["photo_url"] = str(request.url_for("google_place_photo")) + (
            f"?resource={quote(photo_resource, safe='')}&max_height_px=480"
        )
    return LivePlace(**payload)


@router.get("/status", response_model=MapProviderStatus)
async def location_status():
    provider = settings.LOCATION_PROVIDER.strip().lower()
    if provider == "osm":
        return MapProviderStatus(
            configured=True, provider="osm",
            message="OpenStreetMap location services are configured.",
        )
    if provider == "google" and settings.GOOGLE_MAPS_SERVER_KEY:
        return MapProviderStatus(configured=True, provider="google", message="Google Maps is configured.")
    return MapProviderStatus(
        configured=False, provider=provider or "none",
        message="Location intelligence is not configured.",
    )


@router.get("/properties/{property_id}/nearby", response_model=LiveNearbyResponse)
async def nearby(
    property_id: int,
    request: Request,
    category: str = Query(..., pattern=_CATEGORIES),
    radius_km: float = Query(3.0, gt=0, le=50),
    travel_mode: str = Query("WALK", pattern="^(DRIVE|WALK|BICYCLE|TRANSIT)$"),
    include_travel: bool = Query(True),
    db=Depends(get_db),
):
    prop = PropertyRepository(db).get_by_id(property_id)
    if not prop or not prop.is_active:
        raise HTTPException(status_code=404, detail="Property not found")
    if prop.latitude is None or prop.longitude is None:
        raise HTTPException(status_code=422, detail="Property coordinates are unavailable")
    try:
        provider = _provider()
        places = provider.nearby(prop.latitude, prop.longitude, category, radius_km)
        if include_travel:
            for place in places[:5]:
                if place.get("latitude") is None or place.get("longitude") is None:
                    continue
                try:
                    route = provider.route(
                        (prop.latitude, prop.longitude),
                        (place["latitude"], place["longitude"]), travel_mode,
                    )
                    place["distance_km"] = route["distance_km"]
                    place["travel_minutes"] = route["duration_minutes"]
                    place["travel_mode"] = route["mode"]
                except LocationProviderUnavailable as route_error:
                    # A POI remains valid; do not invent a travel time.
                    logger.info("Route enrichment unavailable for %s: %s", place.get("place_id"), route_error)
        source = "OpenStreetMap / Overpass" if provider.name == "osm" else "Google Places API (New)"
        return LiveNearbyResponse(
            property_id=property_id, category=category, radius_km=radius_km,
            source=source, places=[_to_live_place(place, request) for place in places],
        )
    except (LocationProviderUnavailable, LocationProviderInvalidRequest) as exc:
        raise _http_error(exc) from exc


@router.get("/places/{place_id}", response_model=LivePlace)
async def place_details(place_id: str, request: Request):
    provider = _provider()
    if provider.name != "google" or not hasattr(provider, "place_details"):
        raise HTTPException(status_code=501, detail="Place details are not available for the configured provider.")
    try:
        return _to_live_place(provider.place_details(place_id), request)
    except (LocationProviderUnavailable, LocationProviderInvalidRequest) as exc:
        raise _http_error(exc) from exc


@router.get("/photos", name="google_place_photo")
async def google_place_photo(
    resource: str = Query(..., min_length=20), max_height_px: int = Query(480, ge=1, le=480),
):
    provider = _provider()
    if provider.name != "google" or not hasattr(provider, "photo"):
        raise HTTPException(status_code=501, detail="Place photos are not available for the configured provider.")
    try:
        image, content_type = provider.photo(resource, max_height_px)
        return Response(content=image, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})
    except (LocationProviderUnavailable, LocationProviderInvalidRequest) as exc:
        raise _http_error(exc) from exc


@router.post("/geocode", response_model=GeocodeResponse)
async def geocode(data: GeocodeRequest):
    try:
        return GeocodeResponse(**_provider().geocode(data.address))
    except (LocationProviderUnavailable, LocationProviderInvalidRequest) as exc:
        raise _http_error(exc) from exc


@router.post("/routes", response_model=RouteResponse)
async def route(data: RouteRequest):
    try:
        return RouteResponse(**_provider().route(
            (data.origin_latitude, data.origin_longitude),
            (data.destination_latitude, data.destination_longitude), data.travel_mode,
        ))
    except (LocationProviderUnavailable, LocationProviderInvalidRequest) as exc:
        raise _http_error(exc) from exc
