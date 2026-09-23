"""Accommodation discovery policy and query-generation regressions.

These tests use no network and do not turn source fixtures into inventory.
"""
from app.ai.query_parser import parse_query
from app.discovery.query_generation import build_search_queries
from app.discovery.sources import get_source_by_domain, select_sources


def test_hotel_routing_is_bounded_and_excludes_property_portals() -> None:
    intent = parse_query("Find hotels near Hitech City for 2 guests")
    sources = select_sources(intent, limit=4)

    assert 1 <= len(sources) <= 4
    assert all(source.category == "HOTEL" for source in sources)
    assert all(source.page_fetch_allowed is False for source in sources)


def test_unknown_domains_remain_discovery_only() -> None:
    assert get_source_by_domain("unknown-example.invalid") is None


def test_hotel_query_generation_is_bounded_and_category_aware() -> None:
    intent = parse_query("Find hotels near Hyderabad airport for 2 people with breakfast")
    queries = build_search_queries(intent, max_queries=8)

    assert 1 <= len(queries) <= 8
    assert any("hotels" in query for query in queries)
    assert any("2 guests" in query for query in queries)
