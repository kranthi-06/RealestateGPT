"""OpenStreetMap location provider backed by Nominatim, Overpass and OSRM.

The public services are protected with bounded requests, an identifying user
agent, process-local response caching and Nominatim's one-request-per-second
minimum interval. No Google or seeded-place fallback is used here.
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


_CATEGORY_FILTERS: dict[str, list[tuple[str, str]]] = {
    "metro": [("railway", "station"), ("railway", "subway_entrance"), ("public_transport", "station")],
    "hospital": [("amenity", "hospital"), ("amenity", "clinic")],
    "school": [("amenity", "school")],
    "college": [("amenity", "college"), ("amenity", "university")],
    "supermarket": [("shop", "supermarket"), ("shop", "convenience")],
    "mall": [("shop", "mall")],
    "park": [("leisure", "park")],
    "it_park": [("landuse", "commercial"), ("office", "company"), ("industrial", "technology")],
}
_PROFILES = {"DRIVE": "driving", "WALK": "foot", "BICYCLE": "cycling"}


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
_nominatim_lock = threading.Lock()
_last_nominatim_request = 0.0


@dataclass(frozen=True)
class OpenStreetMapLocationProvider:
    """Normalized OSM provider; external responses do not escape this layer."""

    name: str = "osm"

    def geocode(self, address: str) -> dict[str, Any]:
        address = address.strip()
        if not address:
            raise LocationProviderInvalidRequest("An address is required.")
        cache_key = f"geocode:{address.casefold()}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
        self._nominatim_throttle()
        try:
            with self._client() as client:
                response = client.get(
                    f"{settings.NOMINATIM_BASE_URL.rstrip('/')}/search",
                    params={"q": address, "format": "jsonv2", "limit": 1, "addressdetails": 1},
                )
            self._raise_for_status(response, "Nominatim")
            rows = response.json()
        except httpx.HTTPError as exc:
            raise LocationProviderUnavailable("Nominatim is temporarily unavailable.") from exc
        if not rows:
            raise LocationProviderInvalidRequest("OpenStreetMap could not find that address.")
        result = rows[0]
        try:
            normalized = {
                "formatted_address": result["display_name"], "latitude": float(result["lat"]),
                "longitude": float(result["lon"]), "place_id": str(result.get("osm_id") or result.get("place_id")),
                "provider": "nominatim",
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise LocationProviderUnavailable("Nominatim returned an invalid response.") from exc
        _cache.set(cache_key, normalized, 21_600)
        return normalized

    def nearby(self, latitude: float, longitude: float, category: str, radius_km: float = 3.0) -> list[dict[str, Any]]:
        filters = _CATEGORY_FILTERS.get(category)
        if not filters:
            raise LocationProviderInvalidRequest("Unsupported nearby-place category.")
        radius_m = min(max(int(radius_km * 1000), 1), 50_000)
        cache_key = f"nearby:{category}:{latitude:.5f}:{longitude:.5f}:{radius_m}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
        selector = "".join(
            f'nwr["{key}"="{value}"](around:{radius_m},{latitude},{longitude});'
            for key, value in filters
        )
        query = f"[out:json][timeout:20];({selector});out center tags;"
        try:
            with self._client() as client:
                response = client.post(settings.OVERPASS_URL, data={"data": query})
            self._raise_for_status(response, "Overpass")
            elements = response.json().get("elements", [])
        except httpx.HTTPError as exc:
            raise LocationProviderUnavailable("OpenStreetMap nearby-place service is temporarily unavailable.") from exc
        places = [self._place(element, latitude, longitude) for element in elements]
        places = [place for place in places if place is not None]
        places.sort(key=lambda item: item["distance_km"])
        normalized = places[:8]
        _cache.set(cache_key, normalized, 300)
        return normalized

    def route(self, origin: tuple[float, float], destination: tuple[float, float], travel_mode: str = "DRIVE") -> dict[str, Any]:
        mode = travel_mode.upper()
        profile = _PROFILES.get(mode)
        if profile is None:
            raise LocationProviderInvalidRequest("OSRM does not provide public-transit routes.")
        origin_lat, origin_lon = origin
        destination_lat, destination_lon = destination
        cache_key = f"route:{profile}:{origin_lat:.5f}:{origin_lon:.5f}:{destination_lat:.5f}:{destination_lon:.5f}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
        coordinates = f"{origin_lon},{origin_lat};{destination_lon},{destination_lat}"
        try:
            with self._client() as client:
                response = client.get(
                    f"{settings.OSRM_BASE_URL.rstrip('/')}/route/v1/{profile}/{quote(coordinates, safe=',;')}",
                    params={"overview": "false", "alternatives": "false", "steps": "false"},
                )
            self._raise_for_status(response, "OSRM")
            route = (response.json().get("routes") or [None])[0]
        except httpx.HTTPError as exc:
            raise LocationProviderUnavailable("OSRM routing is temporarily unavailable.") from exc
        if not route or route.get("distance") is None or route.get("duration") is None:
            raise LocationProviderUnavailable("OSRM returned no route for these locations.")
        normalized = {
            "distance_km": round(float(route["distance"]) / 1000, 2),
            "duration_minutes": round(float(route["duration"]) / 60, 1),
            "mode": mode.lower(), "provider": "osrm",
        }
        _cache.set(cache_key, normalized, 300)
        return normalized

    @staticmethod
    def _client() -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(settings.OSM_TIMEOUT_SECONDS),
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT, "Accept": "application/json"},
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response, provider: str) -> None:
        if response.status_code == 429:
            raise LocationProviderRateLimited(f"{provider} is rate limiting requests. Please try again shortly.")
        if response.status_code in {400, 404, 422}:
            raise LocationProviderInvalidRequest(f"{provider} could not complete this request.")
        if response.status_code >= 500:
            raise LocationProviderUnavailable(f"{provider} is temporarily unavailable.")
        response.raise_for_status()

    @staticmethod
    def _nominatim_throttle() -> None:
        global _last_nominatim_request
        with _nominatim_lock:
            elapsed = time.monotonic() - _last_nominatim_request
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            _last_nominatim_request = time.monotonic()

    @staticmethod
    def _place(element: dict[str, Any], origin_lat: float, origin_lon: float) -> dict[str, Any] | None:
        tags = element.get("tags") or {}
        latitude = element.get("lat") or (element.get("center") or {}).get("lat")
        longitude = element.get("lon") or (element.get("center") or {}).get("lon")
        if latitude is None or longitude is None:
            return None
        latitude, longitude = float(latitude), float(longitude)
        name = tags.get("name") or tags.get("name:en")
        if not name:
            return None
        kind, osm_id = element.get("type"), element.get("id")
        place_id = f"{kind}/{osm_id}"
        address_parts = [tags.get(key) for key in ("addr:housenumber", "addr:street", "addr:suburb", "addr:city") if tags.get(key)]
        return {
            "provider": "openstreetmap", "place_id": place_id, "name": name,
            "address": ", ".join(address_parts) or None, "latitude": latitude, "longitude": longitude,
            "maps_url": f"https://www.openstreetmap.org/{place_id}", "attributions": [],
            "distance_km": _haversine_km(origin_lat, origin_lon, latitude, longitude),
        }
