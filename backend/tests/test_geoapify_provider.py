"""Contract tests for normalized Geoapify provider responses."""

import httpx
import pytest

from app.providers.location import LocationProviderInvalidRequest, LocationProviderRateLimited
from app.providers.location import get_location_provider
from app.providers.geoapify.provider import GeoapifyLocationProvider
from app.core.config import settings


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


@pytest.fixture(autouse=True)
def mock_geoapify_key(monkeypatch):
    """Ensure GEOAPIFY_API_KEY is set for all tests."""
    monkeypatch.setattr(settings, "GEOAPIFY_API_KEY", "test-key")


def test_geocode_normalizes_geoapify_response(monkeypatch):
    provider = GeoapifyLocationProvider()
    monkeypatch.setattr(GeoapifyLocationProvider, "_client", staticmethod(lambda: _Client(_response({
        "features": [{
            "type": "Feature",
            "properties": {
                "formatted": "HITEC City, Hyderabad, Telangana 500081, India",
                "place_id": "5123456789",
                "lat": "17.4435",
                "lon": "78.3772",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [78.3772, 17.4435],
            },
        }],
    }))))

    result = provider.geocode("HITEC City Hyderabad")

    assert result["provider"] == "geoapify"
    assert result["latitude"] == 17.4435
    assert result["longitude"] == 78.3772
    assert result["formatted_address"] == "HITEC City, Hyderabad, Telangana 500081, India"


def test_nearby_normalizes_geoapify_response(monkeypatch):
    provider = GeoapifyLocationProvider()
    monkeypatch.setattr(GeoapifyLocationProvider, "_client", staticmethod(lambda: _Client(_response({
        "features": [{
            "type": "Feature",
            "properties": {
                "name": "Example Hospital",
                "formatted": "Example Hospital, Hyderabad, Telangana, India",
                "place_id": "5123456790",
                "categories": ["healthcare.hospital"],
                "rating": 4.5,
                "reviews_count": 120,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [78.378, 17.444],
            },
        }],
    }))))

    places = provider.nearby(17.4435, 78.3772, "hospital")

    assert places[0]["provider"] == "geoapify"
    assert places[0]["place_id"] == "5123456790"
    assert places[0]["name"] == "Example Hospital"
    assert places[0]["rating"] == 4.5
    assert places[0]["rating_count"] == 120
    assert "Hospital" in places[0]["categories"]


def test_route_normalizes_geoapify_response(monkeypatch):
    provider = GeoapifyLocationProvider()
    monkeypatch.setattr(GeoapifyLocationProvider, "_client", staticmethod(lambda: _Client(_response({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "distance": 1250,
                "time": 420,
            },
        }],
    }))))

    route = provider.route((17.4435, 78.3772), (17.45, 78.38), "WALK")

    assert route == {"distance_km": 1.25, "duration_minutes": 7.0, "mode": "walk", "provider": "geoapify"}


def test_transit_mode_supported(monkeypatch):
    """Geoapify supports transit routing unlike OSM."""
    provider = GeoapifyLocationProvider()
    monkeypatch.setattr(GeoapifyLocationProvider, "_client", staticmethod(lambda: _Client(_response({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"distance": 5000, "time": 1200},
        }],
    }))))

    route = provider.route((17.4435, 78.3772), (17.45, 78.38), "TRANSIT")
    assert route["mode"] == "transit"


def test_rate_limit_is_typed():
    response = httpx.Response(429, request=httpx.Request("GET", "https://example.test"))
    with pytest.raises(LocationProviderRateLimited):
        GeoapifyLocationProvider._raise_for_status(response, "Geoapify")


def test_geoapify_configuration_selected(monkeypatch):
    monkeypatch.setattr(settings, "LOCATION_PROVIDER", "geoapify")

    assert isinstance(get_location_provider(), GeoapifyLocationProvider)


def test_geoapify_requires_api_key(monkeypatch):
    from app.providers.location import LocationProviderUnavailable

    monkeypatch.setattr(settings, "LOCATION_PROVIDER", "geoapify")
    monkeypatch.setattr(settings, "GEOAPIFY_API_KEY", None)

    with pytest.raises(LocationProviderUnavailable):
        get_location_provider()


def test_unsupported_category_raises(monkeypatch):
    provider = GeoapifyLocationProvider()
    monkeypatch.setattr(GeoapifyLocationProvider, "_client", staticmethod(lambda: _Client(_response({"features": []}))))

    with pytest.raises(LocationProviderInvalidRequest):
        provider.nearby(17.4435, 78.3772, "invalid_category")