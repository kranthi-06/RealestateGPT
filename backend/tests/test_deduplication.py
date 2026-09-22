"""Deduplication engine tests (pure unit — no database)."""
from app.models.property import Property
from app.services.property_ingestion_service import (
    DeduplicationEngine,
    DuplicateMatch,
)


def _prop(**overrides) -> Property:
    base = {
        "title": "3BHK Flat in HITEC City",
        "slug": "3bhk-flat-hitec-city",
        "price": 7500000,
        "property_type": "apartment",
        "listing_type": "sale",
        "city": "Hyderabad",
        "locality": "HITEC City",
        "source": "feed_a",
        "source_type": "partner_api",
        "source_id": "L-100",
        "source_listing_id": "L-100",
        "bedrooms": 3,
        "area": 1200,
        "area_sqft": 1200,
        "latitude": 17.4435,
        "longitude": 78.3772,
        "status": "active",
        "is_active": True,
        "is_synthetic": False,
    }
    base.update(overrides)
    return Property.model_validate(base)


def test_primary_match_is_definitive():
    a = _prop()
    b = _prop(source_id="L-100", source_listing_id="L-100", city="Mumbai", bedrooms=9)
    match = DeduplicationEngine().confidence(b, a)
    assert match.method == "primary"
    assert match.confidence == 100.0


def test_identical_secondary_properties_score_high():
    a = _prop(source="feed_a", source_listing_id="A1")
    b = _prop(source="feed_b", source_listing_id="B1")
    match = DeduplicationEngine().confidence(b, a)
    assert match.method == "secondary"
    assert match.confidence >= 90.0  # auto-merge threshold


def test_completely_different_properties_score_low():
    a = _prop(source_listing_id="X1")
    b = _prop(
        source_listing_id="Y1", city="Mumbai", bedrooms=1,
        price=100000, area=300, latitude=19.0, longitude=72.8,
    )
    match = DeduplicationEngine().confidence(b, a)
    assert match.confidence < 60.0


def test_same_address_different_bedrooms_flags_review_zone():
    address = "Plot 12, Hitech City Main Road, Gachibowli, Hyderabad"
    a = _prop(source_listing_id="R1",
              address=address,
              bedrooms=2, price=6000000, area=1000)
    b = _prop(
        source_listing_id="R2",
        address=address + " (2nd listing)",
        bedrooms=3, price=7500000, area=1200,
        latitude=a.latitude, longitude=a.longitude,
        source="feed_z",
    )
    match = DeduplicationEngine().confidence(b, a)
    assert 60.0 <= match.confidence < 90.0  # review band


def test_normalize_address_is_case_and_noise_insensitive():
    engine = DeduplicationEngine()
    assert engine.normalize_address("Plot 12, Main Road, Hyderabad") == engine.normalize_address("plot 12 main road HYDERABAD")


def test_haversine_proximity():
    close = DeduplicationEngine.haversine_km(17.4435, 78.3772, 17.4436, 78.3773)
    assert close is not None and close < 0.1
    far = DeduplicationEngine.haversine_km(17.4435, 78.3772, 19.0760, 72.8777)
    assert far is not None and far > 500