"""DISCOVERY domain tests: query generation from SearchIntent, conservative
candidate extraction (price/BHK/area/location/structured/missing fields),
deduplication and deterministic ranking. DB-free and fast.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.ai.query_parser import parse_query
from app.discovery.deduplication import canonical_url, find_duplicates
from app.discovery.extractor import PropertyCandidateExtractor
from app.discovery.models import PropertyCandidate
from app.discovery.query_generation import build_search_queries
from app.discovery.ranking import score_candidate
from app.providers.web_search.models import WebSearchResult


def _result(**overrides) -> WebSearchResult:
    defaults = dict(
        id="r1",
        title="2 BHK Apartment in Gachibowli Hyderabad",
        url="https://www.exampleportal.com/listings/2bhk-gachibowli-123",
        domain="exampleportal.com",
        source_name="ExamplePortal",
        description="2 BHK apartment for rent near metro.",
        provider="brave",
        retrieved_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return WebSearchResult(**defaults)


# ─── Query generation ───────────────────────────────────────────────────────

def test_query_generation_uses_intent_and_stays_bounded():
    intent = parse_query("2 BHK for rent under 30000 near metro in Hyderabad")
    queries = build_search_queries(intent, max_queries=3)
    assert len(queries) == 3
    assert queries[0] == "2 BHK for rent under 30000 in Hyderabad"
    assert any("near metro" in q for q in queries)
    assert len(build_search_queries(intent, max_queries=1)) == 1


def test_query_generation_dedupes():
    intent = parse_query("apartment for rent in Pune")
    queries = build_search_queries(intent, max_queries=5)
    assert len(queries) == len(set(queries))


def test_query_generation_never_exceeds_max():
    intent = parse_query("3 BHK villa for sale near school in Bangalore")
    assert len(build_search_queries(intent, max_queries=2)) == 2
    assert len(build_search_queries(intent, max_queries=100)) <= 5


# ─── Extraction ─────────────────────────────────────────────────────────────

def test_extract_price_bhk_area_location():
    result = _result(
        description="2 BHK apartment for rent. Rent Rs. 28000 per month, 1250 sqft, semi-furnished.",
    )
    candidate = PropertyCandidateExtractor().extract(result, intent_city="Hyderabad")
    assert candidate is not None
    assert candidate.price == 28000.0
    assert candidate.transaction_type == "rent"
    assert candidate.bedrooms == 2
    assert candidate.area == 1250.0
    assert candidate.area_unit == "sqft"
    assert candidate.city == "Hyderabad"
    assert candidate.furnishing == "semi-furnished"
    assert candidate.url == result.url


def test_extract_sale_price_lakh_and_crore():
    extractor = PropertyCandidateExtractor()
    sale = _result(description="3 BHK flat for sale at Rs 75 lakh in Kondapur")
    candidate = extractor.extract(sale, intent_city="Hyderabad")
    assert candidate.price == 7_500_000.0
    assert candidate.transaction_type == "sale"

    crores = _result(description="Luxury villa 4 BHK 1.2 crore in Hyderabad")
    candidate = extractor.extract(crores, intent_city="Hyderabad")
    assert candidate.price == 12_000_000.0
def test_extract_missing_fields_stay_missing():
    result = _result(title="New project launch announcement", description="Spacious living spaces.", url="https://www.otherportal.com/new-flats")
    candidate = PropertyCandidateExtractor().extract(result)
    assert candidate is not None
    assert candidate.price is None
    assert candidate.bedrooms is None
    assert candidate.area is None
    assert candidate.image_url is None
    assert candidate.city is None


def test_extract_structured_schema_metadata():
    schema = {
        "name": "2 BHK Apartment",
        "price": "28000",
        "bedrooms": 2,
        "floorSize": "1250 sqft",
        "offers": {"price": "28000"},
    }
    result = _result(schemas=[schema], description="no price in text")
    candidate = PropertyCandidateExtractor().extract(result)
    assert candidate.price == 28000.0
    assert candidate.bedrooms == 2
    assert candidate.area == 1250.0
    assert candidate.extraction_method in ("schema", "mixed")
    assert candidate.extraction_method != "snippet"


def test_extract_malformed_schema_is_ignored():
    result = _result(schemas=[{"price": "not-a-number"}, {"offers": {"price": None}}])
    candidate = PropertyCandidateExtractor().extract(result)
    assert candidate is not None
    assert candidate.price is None


# ─── Deduplication ──────────────────────────────────────────────────────────

def test_canonical_url_strips_tracking_and_fragments():
    a = canonical_url("https://www.example.com/p/x?utm_source=1&id=5&gclid=abc#frag")
    b = canonical_url("https://example.com/p/x?id=5")
    assert a == b


def test_dedupe_by_url_keeps_first_and_drops_duplicate():
    c1 = PropertyCandidate(title="Same listing", url="https://www.exampleportal.com/l/1?utm_source=x", source_domain="exampleportal.com")
    c2 = PropertyCandidate(title="Same listing", url="https://www.exampleportal.com/l/1?utm_source=y", source_domain="exampleportal.com")
    unique, duplicates = find_duplicates([c1, c2])
    assert len(unique) == 1
    assert len(duplicates) == 1


def test_dedupe_never_merges_across_sources():
    a = PropertyCandidate(title="2 BHK Kondapur", url="https://portal-a.com/l/1", source_domain="portal-a.com")
    b = PropertyCandidate(title="2 BHK Kondapur", url="https://portal-b.com/l/1", source_domain="portal-b.com")
    unique, duplicates = find_duplicates([a, b])
    assert len(unique) == 2
    assert len(duplicates) == 0


def test_dedupe_by_source_listing_id():
    shared = "listing-42"
    a = PropertyCandidate(title="A", url="https://portal-a.com/property/listing-42", source_domain="portal-a.com", source_listing_id=shared)
    b = PropertyCandidate(title="B", url="https://portal-a.com/property/listing-42?ref=2", source_domain="portal-a.com", source_listing_id=shared)
    unique, duplicates = find_duplicates([a, b])
    assert len(unique) == 1
    assert len(duplicates) == 1


# ─── Ranking ────────────────────────────────────────────────────────────────

def test_ranking_prefers_matching_budget_and_bedrooms():
    intent = parse_query("2 BHK for rent under 30000 in Hyderabad")
    good = PropertyCandidate(title="2 BHK Apartment Gachibowli Hyderabad", url="https://a.com/1", source_domain="a.com", price=28000, bedrooms=2, transaction_type="rent", city="Hyderabad", discovered_at=datetime.now(timezone.utc))
    bad = PropertyCandidate(title="4 BHK Luxury Penthouse", url="https://b.com/2", source_domain="b.com", price=90000, bedrooms=4, transaction_type="rent", city="Hyderabad", discovered_at=datetime.now(timezone.utc))
    score_good = score_candidate(good, intent)["score"]
    score_bad = score_candidate(bad, intent)["score"]
    assert 0 <= score_good <= 100
    assert score_good > score_bad


def test_ranking_is_deterministic():
    intent = parse_query("apartments in Hyderabad")
    candidate = PropertyCandidate(title="Apartment in Jubilee Hills Hyderabad", url="https://a.com/1", source_domain="a.com", city="Hyderabad")
    first = score_candidate(candidate, intent)
    second = score_candidate(candidate, intent)
    assert first == second