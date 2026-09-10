"""Regression tests for deterministic natural-language query parsing."""

from app.ai.query_parser import parse_query


def test_preserves_property_type_with_nearby_requirement() -> None:
    query = parse_query("Find a 2BHK apartment in Hyderabad under 70 lakh within 2 km of metro")

    assert query.property_type == "apartment"
    assert query.city == "Hyderabad"
    assert query.bedrooms == 2
    assert query.max_price == 7_000_000
    assert [(item.type, item.max_distance_km) for item in query.nearby_requirements] == [
        ("metro", 2.0)
    ]


def test_uses_tightest_repeated_nearby_distance() -> None:
    query = parse_query("A villa in Pune within 4 km of metro and within 2 km of metro")

    assert query.property_type == "villa"
    assert [(item.type, item.max_distance_km) for item in query.nearby_requirements] == [
        ("metro", 2.0)
    ]
