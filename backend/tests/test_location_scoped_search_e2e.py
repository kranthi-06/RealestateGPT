"""End-to-end test of location-scoped unified search.

Patches only the location provider (so no live Nominatim/Tavily calls) and
verifies that a granted location propagates into the web-discovery queries
that the search endpoint actually issues.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_market_and_finance import _FindOnlyDb


class _RecordingProvider:
    """Location provider stub that records the nearby/geocode calls."""

    name = "osm"

    def __init__(self, reverse: dict) -> None:
        self._reverse = reverse
        self.reverse_calls: list[tuple[float, float]] = []

    def reverse_geocode(self, latitude: float, longitude: float) -> dict:
        self.reverse_calls.append((latitude, longitude))
        return dict(self._reverse)

    def geocode(self, address: str) -> dict:
        return {"latitude": 15.5048, "longitude": 78.3756, "formatted_address": address}

    def nearby(self, *_a, **_k):
        return []

    def route(self, *_a, **_k):
        return {"distance_km": 1.0, "duration_minutes": 5.0, "mode": "DRIVE"}


NANDYAL_AREA = {
    "formatted_address": "Panyam, Andhra Pradesh, India",
    "city": "Panyam",
    "county": "Panyam",
    "state": "Andhra Pradesh",
    "latitude": 15.5048,
    "longitude": 78.3756,
}


@pytest.fixture
def client():
    return TestClient(app)


def test_unified_search_scopes_web_discovery_to_the_granted_location(client):
    """The reported bug: '1 BHK' returned Bangalore/Chennai results."""
    provider = _RecordingProvider(NANDYAL_AREA)

    captured_queries: list[list[str]] = []

    class _RecordingDiscovery:
        def __init__(self, db, provider_factory=None):
            pass

        def discover(self, intent, **kwargs):
            # Capture what the query builder would emit for this intent.
            from app.discovery.query_generation import build_search_queries

            captured_queries.append(build_search_queries(intent, 3))
            from app.discovery.service import WebDiscoveryOutcome

            return WebDiscoveryOutcome(
                status="available",
                code="OK",
                message=None,
                cards=[],
                queries_used=captured_queries[0],
                provider="tavily",
            )

    with patch("app.location.service.get_location_provider", return_value=provider), \
         patch("app.discovery.service.WebDiscoveryService", _RecordingDiscovery):
        response = client.post(
            "/api/v1/search/autonomous",
            json={
                "query": "1 BHK",
                "location": {
                    "latitude": 15.5048,
                    "longitude": 78.3756,
                    "radius_km": 5.0,
                },
                "include_web": True,
                "limit": 10,
            },
        )

    assert response.status_code == 200
    body = response.json()

    # The location must have been resolved.
    assert provider.reverse_calls, "reverse geocode was never called"

    # The parsed intent must carry the location AND the state.
    parsed = body["parsed"]
    assert parsed["city"] == "Panyam"
    assert parsed["state"] == "Andhra Pradesh"

    # And every web query must be scoped to that place.
    assert captured_queries, "web discovery never ran"
    for query_list in captured_queries:
        for query in query_list:
            assert "Panyam" in query, f"query not location-scoped: {query!r}"
            assert "Andhra Pradesh" in query, f"missing state: {query!r}"


def test_unified_search_without_location_makes_no_place_claims(client):
    provider = _RecordingProvider(NANDYAL_AREA)
    captured: list[list[str]] = []

    class _RecordingDiscovery:
        def __init__(self, db, provider_factory=None):
            pass

        def discover(self, intent, **kwargs):
            from app.discovery.query_generation import build_search_queries

            captured.append(build_search_queries(intent, 3))
            from app.discovery.service import WebDiscoveryOutcome

            return WebDiscoveryOutcome(status="available", code="OK", cards=[], queries_used=[])

    with patch("app.location.service.get_location_provider", return_value=provider), \
         patch("app.discovery.service.WebDiscoveryService", _RecordingDiscovery):
        response = client.post(
            "/api/v1/search/autonomous",
            json={"query": "1 BHK", "include_web": True, "limit": 10},
        )

    assert response.status_code == 200
    assert not provider.reverse_calls
    assert captured
    for query_list in captured:
        for query in query_list:
            assert "Panyam" not in query
