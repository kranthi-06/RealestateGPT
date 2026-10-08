"""Geoapify location provider backed by Geoapify Geocoding, Places, and Routing APIs.

All requests are server-side with the API key. Responses are normalized to the
LocationProvider contract. Includes response caching, rate limiting, and retries.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.providers.location import (
    LocationProviderInvalidRequest,
    LocationProviderRateLimited,
    LocationProviderUnavailable,
)


_CATEGORY_FILTERS: dict[str, list[str]] = {
    "metro": ["public_transport"],
    "hospital": ["healthcare.hospital"],
    "school": ["education.school"],
    "college": ["education.university", "education.college"],
    "supermarket": ["commercial.supermarket", "commercial.convenience"],
    "mall": ["commercial.shopping_mall"],
    "park": ["leisure.park"],
    "it_park": ["office.company", "office.it"],
    "hotel": ["accommodation.hotel"],
    "restaurant": ["catering.restaurant", "catering.cafe"],
    "bank": ["service.financial.bank", "service.financial.atm"],
    "shopping": ["commercial.shopping_mall", "commercial.supermarket", "commercial.marketplace"],
    "public_transport": ["public_transport"],
    "pharmacy": ["healthcare.pharmacy"],
}

_PROFILES = {
    "DRIVE": "drive",
    "WALK": "walk",
    "BICYCLE": "bicycle",
    "TRANSIT": "transit",
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return round(2 * radius_km * math.asin(math.sqrt(a)), 3)


@dataclass
class _TtlCache:
    values: dict[str, tuple[float, Any]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, key: str) -> Any | None:
        with self.lock:
            item = self.values.get(key)
            if not item or item[0] <= time.monotonic():
                self.values.pop(key, None)
                return None
            return item[1]

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self.lock:
            self.values[key] = (time.monotonic() + ttl_seconds, value)


_cache = _TtlCache()


@dataclass(frozen=True)
class GeoapifyLocationProvider:
    """Normalized Geoapify provider; external responses do not escape this layer."""

    name: str = "geoapify"

    def __post_init__(self) -> None:
        if not settings.GEOAPIFY_API_KEY:
            raise LocationProviderUnavailable("Geoapify API key is not configured.")

    def _api_key(self) -> str:
        return settings.GEOAPIFY_API_KEY

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(settings.GEOAPIFY_TIMEOUT_SECONDS),
            headers={"User-Agent": "RealEstateGPT/1.0", "Accept": "application/json"},
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response, provider: str = "Geoapify") -> None:
        if response.status_code == 429:
            raise LocationProviderRateLimited(f"{provider} is rate limiting requests. Please try again shortly.")
        if response.status_code in {400, 401, 403, 404, 422}:
            raise LocationProviderInvalidRequest(f"{provider} could not complete this request.")
        if response.status_code >= 500:
            raise LocationProviderUnavailable(f"{provider} is temporarily unavailable.")
        response.raise_for_status()

    def geocode(self, address: str) -> dict[str, Any]:
        address = address.strip()
        if not address:
            raise LocationProviderInvalidRequest("An address is required.")
        cache_key = f"geocode:{address.casefold()}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            with self._client() as client:
                response = client.get(
                    f"{settings.GEOAPIFY_BASE_URL.rstrip('/')}/geocode/search",
                    params={
                        "text": address,
                        "limit": 1,
                        "apiKey": self._api_key(),
                    },
                )
            self._raise_for_status(response, "Geoapify Geocoding")
            data = response.json()
        except httpx.HTTPError as exc:
            raise LocationProviderUnavailable("Geoapify Geocoding is temporarily unavailable.") from exc

        features = data.get("features") or []
        if not features:
            raise LocationProviderInvalidRequest("Geoapify could not find that address.")

        feature = features[0]
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []

        try:
            normalized = {
                "formatted_address": props.get("formatted") or address,
                "latitude": float(coordinates[1]) if len(coordinates) > 1 else float(props.get("lat", 0)),
                "longitude": float(coordinates[0]) if len(coordinates) > 0 else float(props.get("lon", 0)),
                "place_id": str(props.get("place_id") or props.get("osm_id") or ""),
                "provider": "geoapify",
            }
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise LocationProviderUnavailable("Geoapify returned an invalid response.") from exc

        _cache.set(cache_key, normalized, 21_600)  # 6 hours
        return normalized

    def nearby(self, latitude: float, longitude: float, category: str, radius_km: float = 3.0) -> list[dict[str, Any]]:
        categories = _CATEGORY_FILTERS.get(category)
        if not categories:
            raise LocationProviderInvalidRequest("Unsupported nearby-place category.")
        radius_m = min(max(int(radius_km * 1000), 1), 50_000)
        cache_key = f"nearby:{category}:{latitude:.5f}:{longitude:.5f}:{radius_m}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            with self._client() as client:
                response = client.get(
                    "https://api.geoapify.com/v2/places",
                    params={
                        "categories": ",".join(categories),
                        "filter": f"circle:{longitude},{latitude},{radius_m}",
                        "limit": 20,
                        "apiKey": self._api_key(),
                    },
                )
            self._raise_for_status(response, "Geoapify Places")
            data = response.json()
        except httpx.HTTPError as exc:
            raise LocationProviderUnavailable("Geoapify Places is temporarily unavailable.") from exc

        features = data.get("features") or []
        places = [self._place(feature, latitude, longitude) for feature in features]
        places = [place for place in places if place is not None]
        places.sort(key=lambda item: item["distance_km"])
        normalized = places[:8]
        _cache.set(cache_key, normalized, 300)  # 5 minutes
        return normalized

    def route(self, origin: tuple[float, float], destination: tuple[float, float], travel_mode: str = "DRIVE") -> dict[str, Any]:
        mode = travel_mode.upper()
        profile = _PROFILES.get(mode)
        if profile is None:
            raise LocationProviderInvalidRequest("Geoapify does not support this travel mode.")
        origin_lat, origin_lon = origin
        destination_lat, destination_lon = destination
        cache_key = f"route:{profile}:{origin_lat:.5f}:{origin_lon:.5f}:{destination_lat:.5f}:{destination_lon:.5f}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            with self._client() as client:
                response = client.get(
                    "https://api.geoapify.com/v1/routing",
                    params={
                        "apiKey": self._api_key(),
                        "waypoints": f"{origin_lat},{origin_lon}|{destination_lat},{destination_lon}",
                        "mode": profile,
                    },
                )
            self._raise_for_status(response, "Geoapify Routing")
            data = response.json()
        except httpx.HTTPError as exc:
            raise LocationProviderUnavailable("Geoapify Routing is temporarily unavailable.") from exc

        features = data.get("features") or []
        if not features:
            raise LocationProviderUnavailable("Geoapify returned no route for these locations.")

        route_props = features[0].get("properties") or {}
        distance_m = route_props.get("distance")
        duration_s = route_props.get("time")

        if distance_m is None or duration_s is None:
            raise LocationProviderUnavailable("Geoapify returned an incomplete route response.")

        normalized = {
            "distance_km": round(float(distance_m) / 1000, 2),
            "duration_minutes": round(float(duration_s) / 60, 1),
            "mode": mode.lower(),
            "provider": "geoapify",
        }
        _cache.set(cache_key, normalized, 300)  # 5 minutes
        return normalized

    def _place(self, feature: dict[str, Any], origin_lat: float, origin_lon: float) -> dict[str, Any] | None:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []

        if len(coordinates) < 2:
            return None
        latitude, longitude = float(coordinates[1]), float(coordinates[0])

        name = props.get("name") or props.get("formatted")
        if not name:
            return None

        place_id = str(props.get("place_id") or props.get("osm_id") or f"{latitude},{longitude}")

        address_parts = [
            props.get("street"),
            props.get("city"),
            props.get("state"),
            props.get("country"),
        ]
        address = ", ".join([p for p in address_parts if p]) or props.get("formatted")

        categories = props.get("categories") or []
        category_labels = [c.split(".")[-1].replace("_", " ").title() for c in categories]

        return {
            "provider": "geoapify",
            "place_id": place_id,
            "name": name,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "categories": category_labels,
            "rating": props.get("rating"),
            "rating_count": props.get("reviews_count"),
            "maps_url": f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=18/{latitude}/{longitude}",
            "attributions": ["Geoapify", "OpenStreetMap contributors"],
            "distance_km": _haversine_km(origin_lat, origin_lon, latitude, longitude),
        }