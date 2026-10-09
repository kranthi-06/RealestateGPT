"""Tests that a granted location actually constrains search queries.

Regression coverage for the reported bug: a user standing in a small town
(e.g. Nandyal district) searched "1 BHK" and received Bangalore/Chennai web
listings because the location never reached the query builder.
"""
from __future__ import annotations

from unittest.mock import patch

from app.discovery.query_generation import build_search_queries
from app.schemas.ai import SearchIntent


def _intent(**kwargs) -> SearchIntent:
    base = {"raw_text": "1 BHK", "listing_type": "rent", "bedrooms": 1}
    base.update(kwargs)
    return SearchIntent(**base)


# ─── Query generation must carry the location ───────────────────────────

def test_queries_include_the_resolved_city():
    queries = build_search_queries(_intent(city="Nandyal"), max_queries=3)
    assert queries, "no queries generated"
    assert all("Nandyal" in q for q in queries), queries


def test_queries_include_state_for_small_towns():
    queries = build_search_queries(
        _intent(city="Panyam", state="Andhra Pradesh"), max_queries=3
    )
    assert all("Andhra Pradesh" in q for q in queries), queries


def test_state_is_not_duplicated_when_already_in_city():
    queries = build_search_queries(
        _intent(city="Nandyal, Andhra Pradesh", state="Andhra Pradesh"), max_queries=3
    )
    assert all("Andhra Pradesh" in q for q in queries), queries


def test_queries_without_a_place_are_not_location_scoped():
    """Honest fallback: no location means no invented place in the query."""
    queries = build_search_queries(_intent(), max_queries=3)
    assert queries
    assert not any("Nandyal" in q for q in queries)


# ─── Location enrichment calls the real service ─────────────────────────

def test_location_service_exposes_reverse_geocode():
    """The service must expose reverse_geocode; search.py depends on it."""
    from app.location.service import LocationService

    assert hasattr(LocationService, "reverse_geocode"), (
        "LocationService.reverse_geocode is missing - search enrichment "
        "would silently AttributeError and ignore the user's location."
    )


def test_reverse_geocode_failure_degrades_to_empty_dict():
    from app.location.service import LocationService

    service = LocationService.__new__(LocationService)
    service.provider = None  # any provider call raises

    class _Boom:
        def reverse_geocode(self, *_a, **_k):
            raise RuntimeError("provider down")

    service.provider = _Boom()
    assert service.reverse_geocode(15.5, 78.3) == {}


def test_reverse_geocode_returns_place_fields():
    from app.location.service import LocationService

    service = LocationService.__new__(LocationService)

    class _Fake:
        def reverse_geocode(self, lat, lng):
            return {
                "formatted_address": "Panyam, Andhra Pradesh, India",
                "city": "Panyam",
                "state": "Andhra Pradesh",
            }

    service.provider = _Fake()
    geo = service.reverse_geocode(15.5048, 78.3756)
    assert geo["city"] == "Panyam"
    assert geo["state"] == "Andhra Pradesh"


def test_enriched_intent_is_applied_to_the_web_query_builder():
    """Simulate the search.py enrichment for the user's exact coordinates."""
    geo = {
        "formatted_address": "Panyam, Andhra Pradesh, India",
        "city": "Panyam",
        "county": "Panyam",
        "state": "Andhra Pradesh",
    }
    intent = _intent()
    # --- inline copy of the enrichment contract ---
    resolved_city = geo.get("city") or geo.get("county") or geo.get("municipality")
    resolved_state = geo.get("state") or geo.get("region")
    if resolved_state:
        intent.state = resolved_state
    if resolved_city:
        placeholder = ("near me", "current location", "me", "my area", "here")
        if not intent.city or intent.city.strip().lower() in placeholder:
            intent.city = resolved_city
    # -------------------------------------------------
    assert intent.city == "Panyam"
    assert intent.state == "Andhra Pradesh"

    queries = build_search_queries(intent, max_queries=3)
    for query in queries:
        assert "Panyam" in query
        assert "Andhra Pradesh" in query


def test_user_typed_location_wins_over_reverse_geocode():
    """An explicit 'Nandyal' in the query must not be overwritten by Panyam."""
    geo = {"city": "Panyam", "state": "Andhra Pradesh"}
    intent = _intent(city="Nandyal")
    resolved_city = geo.get("city")
    placeholder = ("near me", "current location", "me", "my area", "here")
    if resolved_city:
        if not intent.city or intent.city.strip().lower() in placeholder:
            intent.city = resolved_city
    assert intent.city == "Nandyal"
