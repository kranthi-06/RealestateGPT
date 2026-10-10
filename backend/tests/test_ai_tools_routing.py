"""Tests for the AI assistant tool routing.

Verifies that the new Market Intelligence and location-based facility tools
route to the correct services, return real data when present, and explicitly
report "no data" rather than fabricating numbers.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.tools import (
    LocationNearbyInput,
    MarketStatsInput,
    execute_tool,
    get_tool,
    list_tool_descriptions,
)
from app.ai.tool_registry import ToolRegistry
from tests.test_market_and_finance import _FindOnlyDb, _listing


# ─── Registry ───────────────────────────────────────────────────────────

def test_new_tools_are_registered_and_exposed_to_the_model():
    registry = ToolRegistry()
    names = {definition["function"]["name"] for definition in registry.definitions()}
    assert "get_market_stats" in names
    assert "find_nearby_places_by_location" in names


def test_registry_rejects_unknown_tools():
    registry = ToolRegistry()
    with pytest.raises(Exception):
        registry.execute(_FindOnlyDb([]), None, "delete_everything", "{}")


def test_registry_validates_tool_arguments():
    registry = ToolRegistry()
    # A negative radius must be rejected by the pydantic model.
    with pytest.raises(Exception):
        registry.execute(
            _FindOnlyDb([]), None, "find_nearby_places_by_location",
            '{"location": "Nandyal", "radius_km": -5}',
        )


# ─── Market stats tool ──────────────────────────────────────────────────

def test_market_stats_returns_measured_data():
    docs = [_listing(city="Nandyal", price=4000000 + i * 100000) for i in range(5)]
    result = execute_tool(_FindOnlyDb(docs), None, "get_market_stats", {
        "city": "Nandyal", "listing_type": "sale",
    })
    assert result["status"] == "ok"
    assert result["totals"]["listings"] == 5
    assert result["apartments"]["prices"]["median"] == 4200000.0
    assert result["apartments"]["prices"]["is_measured"] is True


def test_market_stats_reports_no_data_instead_of_inventing_prices():
    result = execute_tool(_FindOnlyDb([]), None, "get_market_stats", {"city": "Atlantis"})
    assert result["status"] == "no_catalogue_data"
    assert result["totals"]["listings"] == 0
    assert result["apartments"]["prices"]["median"] is None
    # The message must instruct the model not to estimate.
    assert "cannot be reported" in result["message"]


def test_market_stats_attaches_external_research_for_unknown_locations():
    """When the catalogue is empty, external research is attempted and attached.

    Unit tests are hermetic (no network): the feature reports
    ``not_configured`` honestly — never fabricate a figure. Live retrieval is
    covered by tests/test_external_market_research.py with explicit fakes.
    """
    result = execute_tool(_FindOnlyDb([]), None, "get_market_stats", {"city": "Atlantis"})
    assert "external" in result
    assert result["external"]["status"] == "not_configured"
    stats = (result["external"].get("statistics") or {})
    assert stats.get("data_class", "external_observation") in ("external_observation", "")


def test_market_stats_flags_small_samples():
    docs = [_listing(city="Tinyville", price=900000)]
    result = execute_tool(_FindOnlyDb(docs), None, "get_market_stats", {"city": "Tinyville"})
    assert result["status"] == "ok"
    assert result["apartments"]["prices"]["is_measured"] is False
    assert "indicative only" in result["message"]


def test_market_stats_requires_a_location():
    result = execute_tool(_FindOnlyDb([]), None, "get_market_stats", {})
    assert result["status"] == "invalid"


def test_market_stats_input_rejects_bad_listing_type():
    with pytest.raises(ValidationError):
        MarketStatsInput(city="Nandyal", listing_type="lease")


def test_market_stats_works_for_an_unknown_city():
    """No hardcoded city allow-list may gate the tool."""
    docs = [_listing(city="Some Random Village", price=2500000) for _ in range(4)]
    result = execute_tool(
        _FindOnlyDb(docs), None, "get_market_stats", {"city": "Some Random Village"}
    )
    assert result["status"] == "ok"
    assert result["totals"]["listings"] == 4


def test_market_stats_land_price_per_sq_yard_is_derived():
    docs = [
        _listing(city="Nandyal", property_type="plot", price=1000000, area=500, beds=None)
        for _ in range(4)
    ]
    result = execute_tool(_FindOnlyDb(docs), None, "get_market_stats", {"city": "Nandyal"})
    land = result["land"]
    # 1000000 / 500 sq.ft = 2000/sq.ft; x9 = 18000/sq.yard
    assert land["price_per_sqft"]["median"] == 2000.0
    assert land["price_per_sq_yard"]["median"] == 18000.0


# ─── Location nearby tool ───────────────────────────────────────────────

def test_location_nearby_requires_a_location_or_coordinates():
    result = execute_tool(_FindOnlyDb([]), None, "find_nearby_places_by_location", {})
    assert result["status"] == "invalid"


def test_location_nearby_input_validates_coordinates():
    with pytest.raises(ValidationError):
        LocationNearbyInput(latitude=999, longitude=0)


def test_location_nearby_accepts_a_place_name_and_coordinates():
    assert LocationNearbyInput(location="Nandyal", category="hospital").location == "Nandyal"
    assert LocationNearbyInput(latitude=15.4, longitude=78.4).latitude == 15.4


def test_all_routed_services_are_exposed_as_tools():
    """Every service the assistant must route to is reachable as a tool."""
    definitions = {d["name"] for d in list_tool_descriptions()}
    assert "search_properties" in definitions            # MongoDB property search
    assert "search_web_properties" in definitions        # Tavily web discovery
    assert "find_nearby_places_by_location" in definitions  # OSM location services
    assert "get_market_stats" in definitions             # Market Intelligence
    assert "calculate_affordability" in definitions      # affordability calculator
    assert "calculate_emi" in definitions


def test_unknown_tool_is_rejected():
    with pytest.raises(ValueError):
        execute_tool(_FindOnlyDb([]), None, "nonexistent_tool", {})
