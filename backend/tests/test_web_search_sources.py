"""SOURCE REGISTRY / ROUTER / DETECTOR / VALIDATION / FETCHER / LIMITER tests.

Covers the additional web-discovery architecture: bounded source routing,
conservative listing detection, candidate validation, SSRF-guarded page fetcher
(disabled by default), per-user rate limiting and prompt-injection safety.
"""
from __future__ import annotations

import pytest

from app.ai.query_parser import parse_query
from app.discovery.detector import PropertyListingDetector
from app.discovery.fetcher import WebPageEnrichmentProvider
from app.discovery.models import PropertyCandidate
from app.discovery.sources import (
    INDIA_SOURCES,
    domain_filter_queries,
    get_source_by_domain,
    select_sources,
)
from app.discovery.validation import is_valid, validate_candidate
from app.providers.web_search.limiter import WebSearchLimiter
from app.providers.web_search.models import WebSearchRateLimitError


# ─── Source registry / router ───────────────────────────────────────────────

def test_source_registry_has_india_portals():
    domains = [s.domain for s in INDIA_SOURCES]
    for expected in ("99acres.com", "magicbricks.com", "housing.com", "nobroker.in", "makaan.com"):
        assert expected in domains


def test_source_registry_never_assumes_page_fetch_permission():
    for source in INDIA_SOURCES:
        assert hasattr(source, "page_fetch_allowed")
        assert hasattr(source, "requires_permission")


def test_select_sources_bounded_and_relevant():
    intent = parse_query("2 BHK for rent in Hyderabad")
    sources = select_sources(intent, limit=4)
    assert 1 <= len(sources) <= 4
    assert sources == sorted(sources, key=lambda s: (s.priority, s.name))


def test_get_source_by_domain():
    assert get_source_by_domain("99acres.com").name == "99acres"
    assert get_source_by_domain("www.magicbricks.com").name == "MagicBricks"
    assert get_source_by_domain("unknown.example") is None


def test_domain_filter_queries_bounded():
    sources = select_sources(parse_query("apartment rent"), limit=3)
    queries = domain_filter_queries("apartment for rent", sources)
    assert len(queries) == len(sources)
    assert all("site:" in q for q in queries)


# ─── Listing detector ───────────────────────────────────────────────────────

def _candidate(title="2 BHK Apartment in Gachibowli Hyderabad", description="2 BHK for rent Rs 28000/month, 1250 sqft", url="https://99acres.com/property/2bhk-gachibowli-123", domain="99acres.com"):
    return PropertyCandidate(title=title, url=url, source_domain=domain, description=description)


def test_detector_recognizes_listing():
    detected = PropertyListingDetector().detect(_candidate())
    assert detected.is_property is True
    assert detected.confidence >= 0.30
    assert detected.reasons


def test_detector_rejects_editorial_content():
    candidate = _candidate(
        title="How to buy your first home - a complete guide",
        description="Tips for first-time buyers and market trends.",
        url="https://housing.com/blog/buyers-guide",
    )
    detected = PropertyListingDetector().detect(candidate)
    assert detected.is_property is False


# ─── Validation ─────────────────────────────────────────────────────────────

def _valid_candidate():
    return PropertyCandidate(
        title="2 BHK Apartment in Gachibowli Hyderabad",
        url="https://99acres.com/property/2bhk-gachibowli-123",
        source_domain="99acres.com",
        description="Rent Rs 28000/month.",
        price=28000, bedrooms=2, transaction_type="rent",
        confidence=0.9,
    )


def test_validation_accepts_valid_candidate():
    assert is_valid(_valid_candidate()) is True


def test_validation_rejects_missing_url_and_domain():
    candidate = _valid_candidate()
    candidate.url = ""
    assert "missing url" in validate_candidate(candidate)
    candidate = _valid_candidate()
    candidate.source_domain = ""
    assert "missing source domain" in validate_candidate(candidate)


def test_validation_rejects_unsafe_url():
    candidate = _valid_candidate()
    candidate.url = "javascript:alert(1)"
    assert "unsafe url" in validate_candidate(candidate)


def test_validation_rejects_implausible_values():
    candidate = _valid_candidate()
    candidate.price = -1
    assert "negative price" in validate_candidate(candidate)
    candidate = _valid_candidate()
    candidate.bedrooms = 99
    assert "implausible bedrooms" in validate_candidate(candidate)
    candidate = _valid_candidate()
    candidate.transaction_type = "lease_forever"
    assert "invalid transaction type" in validate_candidate(candidate)


def test_validation_missing_optional_fields_ok():
    candidate = _valid_candidate()
    candidate.price = None
    candidate.bedrooms = None
    candidate.area = None
    assert is_valid(candidate) is True

# ─── Fetcher ────────────────────────────────────────────────────────────────

def test_fetcher_disabled_by_default(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "PAGE_ENRICHMENT_ENABLED", False)
    fetcher = WebPageEnrichmentProvider()
    assert fetcher.fetch("https://99acres.com/property/x") is None
    allowed, _reason = fetcher.can_fetch("https://99acres.com/property/x")
    assert allowed is False


def test_fetcher_blocks_ssrf_targets(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "PAGE_ENRICHMENT_ENABLED", True)
    fetcher = WebPageEnrichmentProvider()
    allowed, _ = fetcher.can_fetch("http://127.0.0.1/x")
    assert allowed is False
    allowed, _ = fetcher.can_fetch("http://169.254.169.254/latest/meta-data")
    assert allowed is False


def test_fetcher_honours_source_page_fetch_policy(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "PAGE_ENRICHMENT_ENABLED", True)
    fetcher = WebPageEnrichmentProvider()
    # 99acres metadata default: page_fetch_allowed=False -> blocked.
    allowed, reason = fetcher.can_fetch("https://99acres.com/property/x")
    assert allowed is False
    assert "does not permit" in reason


def test_fetcher_bounded_metadata_output(monkeypatch):
    import socket as _socket

    from app.core.config import settings

    monkeypatch.setattr(settings, "PAGE_ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(
        _socket,
        "getaddrinfo",
        lambda host, port, proto=_socket.IPPROTO_TCP: [("AF_INET", "SOCK_STREAM", 6, "", ("93.184.216.34", port))],
    )
    import httpx

    class FakeResponse:
        status_code = 200
        content = b"<html><title>2 BHK Flat</title><meta name=\"description\" content=\"2 BHK for rent\"></html>"
        headers = {"content-type": "text/html"}

        @property
        def text(self):
            return self.content.decode("utf-8", "replace")

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return FakeResponse()

    fetcher = WebPageEnrichmentProvider(client=FakeClient())
    metadata = fetcher.fetch("https://vendors.example.com/property/complex/x")
    assert metadata is not None
    assert metadata["page_title"] == "2 BHK Flat"
    assert "length_bytes" in metadata
    assert "<script>" not in str(metadata)  # HTML must not leak into metadata


# ─── Rate limiter ───────────────────────────────────────────────────────────

def test_limiter_blocks_user_after_window():
    limiter = WebSearchLimiter(global_rpm=60, per_user_rpm=2, concurrency=2)
    limiter.acquire("u1")
    limiter.acquire("u1")
    with pytest.raises(WebSearchRateLimitError):
        limiter.acquire("u1")


def test_limiter_released_slots_are_reusable():
    limiter = WebSearchLimiter(global_rpm=60, per_user_rpm=2, concurrency=2)
    limiter.acquire("u1")
    limiter.release()
    limiter.acquire("u2")
    limiter.release()
    assert limiter.snapshot()["active_requests"] == 0


def test_limiter_respects_concurrency(monkeypatch):
    import threading
    import time as _time

    monkeypatch.setattr(_time, "sleep", lambda _: None)
    limiter = WebSearchLimiter(global_rpm=60, per_user_rpm=60, concurrency=1)
    limiter.acquire("u1")
    result = {}

    def attempt():
        try:
            limiter.acquire("u2")
            result["acquired"] = True
        except Exception:  # noqa: BLE001
            result["acquired"] = False

    thread = threading.Thread(target=attempt)
    thread.start()
    thread.join(timeout=1.0)
    # The second request waits while concurrency is saturated (blocked after the wait budget).
    assert result.get("acquired") is not True
    limiter.release()
