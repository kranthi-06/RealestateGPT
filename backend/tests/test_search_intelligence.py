"""Deterministic Phase 3 parser and ranking contracts."""
from app.ai.query_parser import parse_query
from app.ai.scoring import ScoreContext, score_property


def test_lakh_crore_bhk_and_metro_intent_normalization():
    intent = parse_query("Find me a 3BHK under 90L near metro in Hyderabad")

    assert intent.city == "Hyderabad"
    assert intent.bedrooms == 3
    assert intent.max_price == 9_000_000
    assert intent.transport_requirement == "metro"

    crore = parse_query("A villa below 1.2 crore in Pune")
    assert crore.max_price == 12_000_000


def test_area_and_commute_normalization():
    intent = parse_query("2 bedroom above 100 sqm within 30 minutes of HITEC City Hyderabad")

    assert intent.min_area == 1076.39
    assert intent.commute_max_minutes == 30
    assert intent.commute_destination == "hitec city hyderabad"


def test_ranking_reasons_are_derived_from_facts():
    result = score_property(
        {"price": 8_000_000, "city": "Hyderabad", "locality": "HITEC City", "property_type": "apartment", "bedrooms": 3, "area_sqft": 1400, "amenities": ["Gym"], "data_quality_score": 90},
        parse_query("3 BHK apartment under 90 lakhs near metro in Hyderabad").model_dump(),
        ScoreContext(nearby={"metro": 0.8}),
    )

    assert result["overall_score"] > 80
    assert "Within requested budget" in result["positive_factors"]
    assert any("Metro is 0.8 km away" in reason for reason in result["positive_factors"])
