"""OpenStreetMap location provider backed by Nominatim, Overpass and OSRM.

The public services are protected with bounded requests, an identifying user
agent, process-local response caching and Nominatim's one-request-per-second
minimum interval. No Google or seeded-place fallback is used here.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

logger = logging.getLogger(__name__)


_CATEGORY_FILTERS: dict[str, list[tuple[str, str]]] = {
    "metro": [("railway", "station"), ("railway", "subway_entrance"), ("public_transport", "station")],
    "hospital": [("amenity", "hospital"), ("amenity", "clinic")],
    "school": [("amenity", "school")],
    "college": [("amenity", "college"), ("amenity", "university")],
    "supermarket": [("shop", "supermarket"), ("shop", "convenience")],
    "mall": [("shop", "mall")],
    "park": [("leisure", "park")],
    "it_park": [("landuse", "commercial"), ("office", "company"), ("industrial", "technology")],
    "hotel": [("tourism", "hotel"), ("tourism", "guest_house")],
    "restaurant": [("amenity", "restaurant"), ("amenity", "cafe"), ("amenity", "fast_food")],
    "bank": [("amenity", "bank"), ("amenity", "atm")],
    "shopping": [("shop", "mall"), ("shop", "department_store"), ("shop", "supermarket"), ("amenity", "marketplace")],
    "pharmacy": [("amenity", "pharmacy")],
    "public_transport": [("railway", "station"), ("amenity", "bus_station"), ("public_transport", "station")],
}
_PROFILES = {"DRIVE": "driving", "WALK": "foot", "BICYCLE": "cycling"}

# Public Overpass mirrors, tried in order. The configured OVERPASS_URL is
# always first so an operator can pin a preferred instance.
#
# Every entry here must be a GLOBAL instance. A regional mirror (for example
# the Switzerland-only overpass.osm.ch) answers 200 with zero elements for
# every query outside its area, which would silently fake "no results"; the
# primary-answer rule below is the second line of defence against that.
_FALLBACK_OVERPASS_URLS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
)


def _overpass_endpoints() -> list[str]:
    """Configured endpoint first, then mirrors (deduplicated)."""
    configured = (settings.OVERPASS_URL or "").strip()
    endpoints = [configured] if configured else []
    endpoints += [url for url in _FALLBACK_OVERPASS_URLS if url != configured]
    return [url for url in endpoints if url]


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

    def reverse_geocode(self, latitude: float, longitude: float) -> dict[str, Any]:
        """Reverse-geocode coordinates via Nominatim (public OSM service)."""
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise LocationProviderInvalidRequest("Coordinates are out of range.")
        cache_key = f"reverse:{latitude:.5f}:{longitude:.5f}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
        self._nominatim_throttle()
        try:
            with self._client() as client:
                response = client.get(
                    f"{settings.NOMINATIM_BASE_URL.rstrip('/')}/reverse",
                    params={"lat": latitude, "lon": longitude, "format": "jsonv2", "addressdetails": 1},
                )
                self._raise_for_status(response, "Nominatim")
            data = response.json()
        except httpx.HTTPError as exc:
            raise LocationProviderUnavailable("Nominatim is temporarily unavailable.") from exc
        if not isinstance(data, dict) or data.get("error") or not data.get("lat"):
            raise LocationProviderInvalidRequest("OpenStreetMap could not reverse-geocode that location.")
        address = data.get("address") or {}
        parts: list[str] = []
        for key in ("suburb", "neighbourhood", "quarter", "village", "town", "city", "county", "state", "country"):
            value = address.get(key)
            if value and value not in parts:
                parts.append(str(value))
        normalized = {
            "formatted_address": ", ".join(parts) or str(data.get("display_name") or ""),
            "latitude": float(data.get("lat")),
            "longitude": float(data.get("lon")),
            "place_id": str(data.get("osm_id") or data.get("place_id") or ""),
            "provider": "nominatim",
            "city": address.get("city") or address.get("town") or address.get("village") or address.get("county"),
            "state": address.get("state"),
            "country": address.get("country"),
            "suburb": address.get("suburb") or address.get("neighbourhood") or address.get("quarter"),
            "county": address.get("county"),
        }
        if not normalized["formatted_address"]:
            normalized["formatted_address"] = f"{latitude:.5f}, {longitude:.5f}"
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
        elements = self._overpass_query(query)
        places = [self._place(element, latitude, longitude) for element in elements]
        places = [place for place in places if place is not None]
        places.sort(key=lambda item: item["distance_km"])
        normalized = places[:8]
        _cache.set(cache_key, normalized, 300)
        return normalized

    @staticmethod
    def _merged_selectors(categories: list[str]) -> list[tuple[str, str]]:
        """Collapse per-category tag filters into one regex selector per key.

        ``nwr["amenity"~"^(bank|clinic|hospital)$"](around:...)`` evaluates as a
        single scan, where one statement per (key, value) pair makes Overpass
        walk the area once per filter. Classification stays exact: bucketing
        afterwards still matches the individual ``_CATEGORY_FILTERS`` values.
        """
        by_key: dict[str, set[str]] = {}
        for category in categories:
            for key, value in _CATEGORY_FILTERS[category]:
                by_key.setdefault(key, set()).add(value)
        return [(key, "|".join(sorted(values))) for key, values in sorted(by_key.items())]

    def nearby_multi(
        self, latitude: float, longitude: float, categories: list[str], radius_km: float = 3.0
    ) -> dict[str, list[dict[str, Any]]]:
        """Nearby places for several categories in ONE Overpass round trip.

        A fan-out of one request per category multiplies the chance of hitting
        the public instances' rate limits, and a category that fails comes back
        as an empty list that is indistinguishable from "nothing mapped here".
        A single union query keeps the pressure at one request and guarantees
        every bucket was produced by the same successful fetch. An element that
        matches several categories (e.g. a mall that is also a supermarket)
        legitimately appears in each of them.
        """
        supported = [category for category in dict.fromkeys(categories) if category in _CATEGORY_FILTERS]
        if not supported:
            raise LocationProviderInvalidRequest("Unsupported nearby-place category.")
        radius_m = min(max(int(radius_km * 1000), 1), 50_000)
        cache_key = (
            f"nearby_multi:{','.join(supported)}:{latitude:.5f}:{longitude:.5f}:{radius_m}"
        )
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
        filters = self._merged_selectors(supported)
        selector = "".join(
            f'nwr["{key}"~"{"^(" + value + ")$"}"](around:{radius_m},{latitude},{longitude});'
            for key, value in filters
        )
        query = f"[out:json][timeout:20];({selector});out center tags;"
        # A generous but bounded budget: every mirror is asked in parallel, so
        # this is wall time, not the sum, and it still fits a function
        # duration even when the public instances are all struggling.
        elements = self._overpass_query(
            query, per_attempt_timeout=20.0, total_budget=25.0
        )
        by_category: dict[str, list[dict[str, Any]]] = {category: [] for category in supported}
        for element in elements:
            tags = element.get("tags") or {}
            matched = [
                category
                for category in supported
                if any(tags.get(key) == value for key, value in _CATEGORY_FILTERS[category])
            ]
            if not matched:
                continue
            place = self._place(element, latitude, longitude)
            if place is None:
                continue
            for category in matched:
                by_category[category].append(place)
        for category in supported:
            by_category[category].sort(key=lambda item: item["distance_km"])
            del by_category[category][8:]
        _cache.set(cache_key, by_category, 300)
        return by_category

    def _overpass_query(
        self,
        query: str,
        *,
        per_attempt_timeout: float | None = None,
        total_budget: float = 20.0,
    ) -> list[dict[str, Any]]:
        """Run an Overpass query against every public mirror at once.

        The public Overpass instances are heavily rate limited and frequently
        return 429/502/503/504, or drop the connection, under load. A
        single-attempt implementation therefore surfaces a 503 to the browser
        for a place that is perfectly well mapped. Policy per outcome:

        * 200 with elements → success; returned as soon as any mirror answers
          with data.
        * 200 with an empty body → only trusted when it comes from the
          configured endpoint, or when every mirror in a round agreed. A
          loaded or regional mirror must not be able to fake "nothing is
          mapped here" while the primary is unavailable.
        * 400/404/422 → a malformed query or unsupported category. Raised as
          an invalid request when no mirror served data, because another
          mirror cannot fix a malformed query.
        * 429 / 5xx / network error → retryable: mirrors are asked in parallel
          and, if every one fails, there is one more short round, because the
          main instance recovers quickly.

        ``total_budget`` bounds the wall time, including the retry round, so a
        deployment never spends its whole function duration on dead mirrors.
        """
        endpoints = [url.rstrip("/") for url in _overpass_endpoints() if url.strip()]
        if not endpoints:
            raise LocationProviderUnavailable("No Overpass endpoint is configured.")
        primary = endpoints[0]

        deadline = time.monotonic() + total_budget
        saw_invalid_request = False
        # Only the configured endpoint may report "nothing is mapped here": a
        # mirror that answers 200 with zero elements while the primary is
        # unavailable must never be able to fake an empty result.
        primary_empty: list[dict[str, Any]] | None = None
        last_error: str | None = None
        for attempt_round in (0, 1):
            if attempt_round:
                remaining = deadline - time.monotonic()
                if remaining <= 0.2:
                    break
                time.sleep(min(0.4, remaining))
            outcomes = self._overpass_attempt_all(
                endpoints, query, per_attempt_timeout, deadline
            )
            round_answered = False
            round_failed = False
            for url, outcome in outcomes:
                kind = outcome[0]
                if kind == "ok":
                    round_answered = True
                    if outcome[1]:
                        # A mirror answered with real data: use it immediately.
                        return outcome[1]
                    if url == primary and primary_empty is None:
                        primary_empty = outcome[1]
                elif kind == "invalid":
                    round_failed = True
                    saw_invalid_request = True
                else:
                    round_failed = True
                    last_error = outcome[1]
            if round_answered and not round_failed:
                # Every mirror answered and none returned data. The empty
                # answer is unanimous, so retrying cannot reveal more.
                return primary_empty if primary_empty is not None else []

        if primary_empty is not None:
            # The configured endpoint consistently reports that nothing is
            # mapped here; that answer is authoritative even if a fallback
            # mirror stayed unhealthy.
            return primary_empty

        if saw_invalid_request:
            raise LocationProviderInvalidRequest(
                "OpenStreetMap could not complete this request."
            )
        logger.info(
            "overpass_all_mirrors_failed endpoints=%s last_error=%s",
            len(endpoints), last_error,
        )
        raise LocationProviderUnavailable(
            "OpenStreetMap nearby-place service is temporarily unavailable."
        )

    def _overpass_attempt_all(
        self,
        endpoints: list[str],
        query: str,
        per_attempt_timeout: float | None,
        deadline: float,
    ) -> list[tuple[str, tuple[Any, ...]]]:
        """POST the query to every mirror in parallel; the data wins.

        Returns a list of ``(url, outcome)`` where outcome is
        ``("ok", elements)``, ``("invalid", status)`` or ``("unavailable",
        reason)``. Asking all mirrors concurrently means one hung instance
        cannot spend the whole request budget before a healthy mirror is even
        asked. The list stops growing as soon as a mirror answers WITH DATA,
        so a fast empty answer cannot pre-empt a slower real one; when every
        mirror has answered, the caller decides between an agreed empty
        result and an error.
        """
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            remaining = 0.5
        # The retry round must not overshoot the budget with a fresh timeout.
        timeout = remaining if per_attempt_timeout is None else min(per_attempt_timeout, remaining)

        def attempt(url: str) -> tuple[str, tuple[Any, ...]]:
            try:
                with self._client(timeout=timeout) as client:
                    response = client.post(url, data={"data": query})
            except httpx.HTTPError as exc:
                return (url, ("unavailable", type(exc).__name__))
            if response.status_code in {400, 404, 422}:
                return (url, ("invalid", response.status_code))
            if response.status_code >= 400:
                return (url, ("unavailable", f"HTTP {response.status_code}"))
            try:
                payload = response.json()
            except ValueError:
                return (url, ("unavailable", "invalid JSON payload"))
            elements = payload.get("elements", []) if isinstance(payload, dict) else []
            return (url, ("ok", elements if isinstance(elements, list) else []))

        pool = ThreadPoolExecutor(max_workers=len(endpoints))
        try:
            futures = [pool.submit(attempt, url) for url in endpoints]
            outcomes: list[tuple[str, tuple[Any, ...]]] = []
            for future in as_completed(futures):
                outcomes.append(future.result())
                # Stop as soon as a mirror answers WITH DATA. An empty answer
                # is not a signal to stop: a loaded mirror can serve that.
                if outcomes[-1][1][0] == "ok" and outcomes[-1][1][1]:
                    return outcomes
            return outcomes
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

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
    def _client(timeout: float | None = None) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(
                timeout if timeout is not None else settings.OSM_TIMEOUT_SECONDS
            ),
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
