"""Official, server-side Google Maps Platform adapter.

This module is the only code allowed to call Google web services. It keeps the
server key in the API process and never persists Google place or photo data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.location.service import haversine_km
from app.providers.location import (
    LocationProvider,
    LocationProviderInvalidRequest,
    LocationProviderRateLimited,
    LocationProviderUnavailable,
)


PLACE_TYPES = {
    "metro": ["subway_station", "train_station", "transit_station"],
    "hospital": ["hospital"], "school": ["school"], "college": ["university"],
    "supermarket": ["supermarket"], "mall": ["shopping_mall"], "park": ["park"],
    "it_park": ["corporate_office"],
}


@dataclass(frozen=True)
class GoogleMapsProvider:
    """Google Places (New), Geocoding and Routes implementation."""

    name = "google"
    key: str
    nearby_fields = (
        "places.id,places.displayName,places.formattedAddress,places.location,"
        "places.rating,places.userRatingCount,places.googleMapsUri,places.photos"
    )
    detail_fields = (
        "id,displayName,formattedAddress,location,rating,userRatingCount,"
        "googleMapsUri,regularOpeningHours,websiteUri,nationalPhoneNumber,photos"
    )

    def __init__(self) -> None:
        if settings.MAPS_PROVIDER.lower() != "google" or not settings.GOOGLE_MAPS_SERVER_KEY:
            raise LocationProviderUnavailable("Google Maps integration is not configured.")
        object.__setattr__(self, "key", settings.GOOGLE_MAPS_SERVER_KEY)

    def nearby(self, latitude: float, longitude: float, category: str, radius_km: float = 3.0) -> list[dict[str, Any]]:
        included_types = PLACE_TYPES.get(category)
        if not included_types:
            raise ValueError("Unsupported nearby-place category")
        payload = {
            "includedTypes": included_types, "maxResultCount": 8, "rankPreference": "DISTANCE",
            "locationRestriction": {"circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": min(max(radius_km * 1000, 1), 50_000)}},
        }
        response = self._request("POST", "https://places.googleapis.com/v1/places:searchNearby", json=payload, headers={"X-Goog-FieldMask": self.nearby_fields})
        return [self._place_payload(place, latitude, longitude) for place in response.get("places", [])]

    def place_details(self, place_id: str) -> dict[str, Any]:
        if not place_id or "/" in place_id:
            raise ValueError("Invalid Google place identifier")
        place = self._request("GET", f"https://places.googleapis.com/v1/places/{place_id}", headers={"X-Goog-FieldMask": self.detail_fields})
        location = place.get("location") or {}
        data = self._place_payload(place, location.get("latitude"), location.get("longitude"))
        data.update({"website_url": place.get("websiteUri"), "phone_number": place.get("nationalPhoneNumber"), "opening_hours": (place.get("regularOpeningHours") or {}).get("weekdayDescriptions", [])})
        return data

    def geocode(self, address: str) -> dict[str, Any]:
        if not address.strip():
            raise ValueError("Address is required")
        response = self._request("GET", "https://maps.googleapis.com/maps/api/geocode/json", params={"address": address})
        if response.get("status") != "OK" or not response.get("results"):
            raise LocationProviderInvalidRequest("Google could not geocode that address.")
        result = response["results"][0]
        location = (result.get("geometry") or {}).get("location") or {}
        return {"formatted_address": result.get("formatted_address"), "latitude": location.get("lat"), "longitude": location.get("lng"), "place_id": result.get("place_id"), "provider": "google"}

    def route(self, origin: tuple[float, float], destination: tuple[float, float], travel_mode: str = "DRIVE") -> dict[str, Any]:
        payload = {"origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}}, "destination": {"location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}}, "travelMode": travel_mode, "units": "METRIC"}
        response = self._request("POST", "https://routes.googleapis.com/directions/v2:computeRoutes", json=payload, headers={"X-Goog-FieldMask": "routes.duration,routes.distanceMeters"})
        route = (response.get("routes") or [{}])[0]
        seconds = self._duration_seconds(route.get("duration", "0s"))
        return {"distance_km": round((route.get("distanceMeters") or 0) / 1000, 2), "duration_minutes": round(seconds / 60, 1), "mode": travel_mode.lower(), "provider": "google"}

    def photo(self, resource_name: str, max_height_px: int = 480) -> tuple[bytes, str]:
        if not resource_name.startswith("places/") or "/photos/" not in resource_name:
            raise ValueError("Invalid Google photo resource")
        url = f"https://places.googleapis.com/v1/{resource_name}/media"
        try:
            with httpx.Client(timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = client.get(url, headers={"X-Goog-Api-Key": self.key}, params={"maxHeightPx": min(max(max_height_px, 1), 480)})
                self._raise_for_status(response)
                content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
                if not content_type.startswith("image/"):
                    raise LocationProviderUnavailable("Google Maps returned an unexpected photo response.")
                return response.content, content_type
        except httpx.HTTPError as exc:
            raise LocationProviderUnavailable("Google Maps service is temporarily unavailable.") from exc

    def _place_payload(self, place: dict[str, Any], origin_latitude: float | None, origin_longitude: float | None) -> dict[str, Any]:
        location = place.get("location") or {}
        latitude, longitude = location.get("latitude"), location.get("longitude")
        photos = place.get("photos") or []
        photo = photos[0] if photos else {}
        distance = None
        if None not in (origin_latitude, origin_longitude, latitude, longitude):
            distance = haversine_km(origin_latitude, origin_longitude, latitude, longitude)
        return {"provider": "google", "place_id": place.get("id"), "name": (place.get("displayName") or {}).get("text") or "Unnamed place", "address": place.get("formattedAddress"), "latitude": latitude, "longitude": longitude, "rating": place.get("rating"), "rating_count": place.get("userRatingCount"), "maps_url": place.get("googleMapsUri"), "photo_resource": photo.get("name"), "attributions": [item.get("displayName") for item in photo.get("authorAttributions", []) if item.get("displayName")], "distance_km": distance}

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"X-Goog-Api-Key": self.key, "Content-Type": "application/json", **kwargs.pop("headers", {})}
        try:
            with httpx.Client(timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS) as client:
                response = client.request(method, url, headers=headers, **kwargs)
                self._raise_for_status(response)
                return response.json()
        except httpx.HTTPError as exc:
            raise LocationProviderUnavailable("Google Maps service is temporarily unavailable.") from exc

    @staticmethod
    def _duration_seconds(value: str) -> float:
        try:
            return float(str(value).removesuffix("s"))
        except ValueError:
            return 0.0

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise LocationProviderRateLimited("Google Maps request limit reached. Please try again shortly.")
        if response.status_code in {400, 403, 404}:
            raise LocationProviderInvalidRequest("Google Maps could not complete this request.")
        response.raise_for_status()
