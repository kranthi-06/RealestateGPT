"""Contract tests for the server-side Google Maps adapter (no live credentials)."""

import httpx
import pytest

from app.providers.google_maps.provider import (
    GoogleMapsProvider,
    LocationProviderRateLimited,
)


def test_nearby_maps_google_response_to_typed_place(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAPS_PROVIDER", "google")
    monkeypatch.setattr(settings, "GOOGLE_MAPS_SERVER_KEY", "test-key")
    provider = GoogleMapsProvider()
    monkeypatch.setattr(GoogleMapsProvider, "_request", lambda *args, **kwargs: {"places": [{
        "id": "google-place-id", "displayName": {"text": "Example Metro"},
        "formattedAddress": "Example Road", "location": {"latitude": 17.44, "longitude": 78.38},
        "rating": 4.3, "userRatingCount": 12, "googleMapsUri": "https://maps.google.com/?cid=1",
        "photos": [{"name": "places/google-place-id/photos/photo-id", "authorAttributions": [{"displayName": "Photographer"}]}],
    }]})

    places = provider.nearby(17.45, 78.39, "metro")

    assert places[0]["name"] == "Example Metro"
    assert places[0]["distance_km"] is not None
    assert places[0]["attributions"] == ["Photographer"]


def test_rate_limit_is_exposed_as_a_distinct_provider_error() -> None:
    response = httpx.Response(429, request=httpx.Request("GET", "https://example.test"))

    with pytest.raises(LocationProviderRateLimited):
        GoogleMapsProvider._raise_for_status(response)
