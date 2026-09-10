"""Official Google Maps Platform web-service adapter.

Only short-lived responses are returned to clients. We do not persist Google
place payloads or photo resource names in the application database.
"""
from __future__ import annotations

from typing import Any
import httpx

from app.core.config import settings

PLACE_TYPES = {
    "metro": ["subway_station", "train_station", "transit_station"],
    "hospital": ["hospital"], "school": ["school"], "college": ["university"],
    "supermarket": ["supermarket"], "mall": ["shopping_mall"], "park": ["park"],
    "it_park": ["corporate_office"], "bank": ["bank"], "pharmacy": ["pharmacy"],
    "restaurant": ["restaurant"],
}


class LocationProviderUnavailable(RuntimeError):
    pass


class GoogleMapsProvider:
    nearby_fields = "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.googleMapsUri,places.photos"

    def __init__(self) -> None:
        if settings.MAPS_PROVIDER != "google" or not settings.GOOGLE_MAPS_SERVER_KEY:
            raise LocationProviderUnavailable("Google Maps integration is not configured.")
        self.key = settings.GOOGLE_MAPS_SERVER_KEY

    def nearby(self, latitude: float, longitude: float, category: str, radius_km: float = 3.0) -> list[dict[str, Any]]:
        types = PLACE_TYPES.get(category)
        if not types:
            raise ValueError("Unsupported nearby-place category")
        payload = {"includedTypes": types, "maxResultCount": 10,
                   "rankPreference": "DISTANCE", "locationRestriction": {"circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": min(radius_km * 1000, 50000)}}}
        response = self._request("POST", "https://places.googleapis.com/v1/places:searchNearby", json=payload,
                                 headers={"X-Goog-FieldMask": self.nearby_fields})
        places = []
        for place in response.get("places", []):
            location = place.get("location") or {}
            photos = place.get("photos") or []
            places.append({"provider": "google", "place_id": place.get("id"), "name": (place.get("displayName") or {}).get("text"),
                           "address": place.get("formattedAddress"), "latitude": location.get("latitude"), "longitude": location.get("longitude"),
                           "rating": place.get("rating"), "maps_url": place.get("googleMapsUri"),
                           "photo_resource": photos[0].get("name") if photos else None,
                           "attributions": [item.get("displayName") for item in (photos[0].get("authorAttributions") or [])] if photos else []})
        return places

    def route(self, origin: tuple[float, float], destination: tuple[float, float], travel_mode: str = "DRIVE") -> dict[str, Any]:
        payload = {"origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
                   "destination": {"location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}},
                   "travelMode": travel_mode, "units": "METRIC"}
        response = self._request("POST", "https://routes.googleapis.com/directions/v2:computeRoutes", json=payload,
                                 headers={"X-Goog-FieldMask": "routes.duration,routes.distanceMeters"})
        route = (response.get("routes") or [{}])[0]
        seconds = int(str(route.get("duration", "0s")).removesuffix("s") or 0)
        return {"distance_km": round((route.get("distanceMeters") or 0) / 1000, 2), "duration_minutes": round(seconds / 60, 1), "mode": travel_mode.lower(), "provider": "google"}

    def _request(self, method: str, url: str, **kwargs) -> dict:
        headers = {"X-Goog-Api-Key": self.key, "Content-Type": "application/json", **kwargs.pop("headers", {})}
        try:
            with httpx.Client(timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS) as client:
                response = client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise LocationProviderUnavailable("Google Maps service is temporarily unavailable.") from exc
