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


def test_classifies_hotel_request_without_calling_it_a_property() -> None:
    query = parse_query(
        "Find hotels near Hyderabad airport for 2 people with breakfast under 5000"
    )

    assert query.category == "HOTEL"
    assert query.listing_type == "rent"
    assert query.guests == 2
    assert query.breakfast_required is True
    assert query.max_price == 5_000


def test_classifies_hostel_and_short_stay_requests() -> None:
    assert parse_query("Find cheap hostels near Hyderabad airport").category == "HOSTEL"
    assert parse_query("Find a weekend stay near Bangalore").category == "SHORT_STAY"


def test_classifies_plural_accommodation_categories() -> None:
    serviced = parse_query("Serviced apartments in Hyderabad with breakfast for 2 guests")
    assert serviced.category == "SERVICED_APARTMENT"
    assert serviced.listing_type == "rent"
    assert serviced.breakfast_required is True

    vacation = parse_query("Vacation rentals in Goa for 4 guests")
    assert vacation.category == "VACATION_RENTAL"
    assert vacation.listing_type == "rent"
    assert vacation.city == "Goa"
    assert vacation.guests == 4

