"""Location-provider contracts and configured-provider selection.

All location routes use this module.  Providers must return normalized data or
raise a typed error; they must never substitute another provider or demo data.
"""
from __future__ import annotations

from typing import Any, Protocol

from app.core.config import settings


class LocationProvider(Protocol):
    name: str

    def nearby(self, latitude: float, longitude: float, category: str, radius_km: float = 3.0) -> list[dict[str, Any]]: ...
    def geocode(self, address: str) -> dict[str, Any]: ...
    def route(self, origin: tuple[float, float], destination: tuple[float, float], travel_mode: str = "DRIVE") -> dict[str, Any]: ...


class LocationProviderUnavailable(RuntimeError):
    """The configured provider cannot currently serve the request."""


class LocationProviderRateLimited(LocationProviderUnavailable):
    """The configured provider requested that calls slow down."""


class LocationProviderInvalidRequest(LocationProviderUnavailable):
    """The configured provider rejected validly-shaped application input."""


def get_location_provider() -> LocationProvider:
    """Create only the provider selected by LOCATION_PROVIDER."""
    provider = settings.LOCATION_PROVIDER.strip().lower()
    if provider == "osm":
        from app.providers.openstreetmap.provider import OpenStreetMapLocationProvider
        return OpenStreetMapLocationProvider()
    if provider == "google":
        from app.providers.google_maps.provider import GoogleMapsProvider
        return GoogleMapsProvider()
    raise LocationProviderUnavailable("The configured location provider is unavailable.")
