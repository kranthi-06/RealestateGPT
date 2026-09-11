"""Contract tests for normalized OpenStreetMap provider responses."""

import httpx
import pytest

from app.providers.location import LocationProviderInvalidRequest, LocationProviderRateLimited
from app.providers.location import get_location_provider
from app.providers.openstreetmap.provider import OpenStreetMapLocationProvider


class _Client:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, *_args, **_kwargs):
        return self.response

    def post(self, *_args, **_kwargs):
        return self.response


def _response(payload):
    return httpx.Response(200, json=payload, request=httpx.Request("GET", "https://example.test"))


def test_geocode_normalizes_nominatim_response(monkeypatch):
    provider = OpenStreetMapLocationProvider()
    monkeypatch.setattr(OpenStreetMapLocationProvider, "_nominatim_throttle", staticmethod(lambda: None))
    monkeypatch.setattr(OpenStreetMapLocationProvider, "_client", staticmethod(lambda: _Client(_response([{
        "display_name": "HITEC City, Hyderabad, Telangana, India", "lat": "17.4435", "lon": "78.3772", "osm_id": 123,
    }]))))

    result = provider.geocode("HITEC City Hyderabad")

    assert result["provider"] == "nominatim"
    assert result["latitude"] == 17.4435


def test_nearby_normalizes_overpass_response(monkeypatch):
    provider = OpenStreetMapLocationProvider()
    monkeypatch.setattr(OpenStreetMapLocationProvider, "_client", staticmethod(lambda: _Client(_response({"elements": [{
        "type": "node", "id": 42, "lat": 17.444, "lon": 78.378,
        "tags": {"name": "Example Hospital", "amenity": "hospital"},
    }]}))))

    places = provider.nearby(17.4435, 78.3772, "hospital")

    assert places[0]["provider"] == "openstreetmap"
    assert places[0]["place_id"] == "node/42"
    assert "rating" not in places[0]


def test_route_normalizes_osrm_response(monkeypatch):
    provider = OpenStreetMapLocationProvider()
    monkeypatch.setattr(OpenStreetMapLocationProvider, "_client", staticmethod(lambda: _Client(_response({"routes": [{"distance": 1250, "duration": 420}]}))))

    route = provider.route((17.4435, 78.3772), (17.45, 78.38), "WALK")

    assert route == {"distance_km": 1.25, "duration_minutes": 7.0, "mode": "walk", "provider": "osrm"}


def test_transit_does_not_silently_fallback_to_driving():
    with pytest.raises(LocationProviderInvalidRequest):
        OpenStreetMapLocationProvider().route((17.4, 78.3), (17.5, 78.4), "TRANSIT")


def test_rate_limit_is_typed():
    response = httpx.Response(429, request=httpx.Request("GET", "https://example.test"))
    with pytest.raises(LocationProviderRateLimited):
        OpenStreetMapLocationProvider._raise_for_status(response, "Overpass")


def test_osm_configuration_never_selects_google(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "LOCATION_PROVIDER", "osm")
    # A future Google key must not alter the selected provider.
    monkeypatch.setattr(settings, "GOOGLE_MAPS_SERVER_KEY", "future-google-key")

    assert isinstance(get_location_provider(), OpenStreetMapLocationProvider)
