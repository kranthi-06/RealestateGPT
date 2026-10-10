"""External market research service tests.

Retrieval is exercised with explicit fake providers (never the network), so
these tests prove the honesty contract: observations are extracted from
retrieved text, statistics come only from those observations, AI summaries are
validated against evidence, and failures produce typed states instead of
fabricated market data.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.services.external_market_service import (
    ExternalMarketService,
    MarketResearchFilter,
)
from app.providers.web_search.models import (
    WebSearchNotConfiguredError,
    WebSearchResponse,
    WebSearchResult,
)
from tests.fake_mongo import FakeDB


class FakeSearchProvider:
    name = "fake-search"

    def __init__(self, results: list[WebSearchResult]):
        self._results = results
        self.calls: list[str] = []

    def search(self, query, country=None, language=None, count=20, offset=0, freshness=None):
        self.calls.append(query)
        return WebSearchResponse(results=self._results, total_results=len(self._results), provider=self.name)


class FailingSearchProvider:
    name = "failing-search"

    def search(self, *args, **kwargs):
        from app.providers.web_search.models import WebSearchUnavailableError

        raise WebSearchUnavailableError("provider is down")


class FakeGeocodeProvider:
    """Geocoder stub: 'X' resolves so research proceeds without the network."""

    name = "fake-geo"

    def geocode(self, address):
        return {
            "formatted_address": f"{address}, Testland",
            "latitude": 12.34,
            "longitude": 56.78,
            "country": "Testland",
            "country_code": "TL",
            "state": "Test State",
            "city": address,
        }


@pytest.fixture(autouse=True)
def _fake_geocoder(monkeypatch):
    import app.providers.location as location_module

    monkeypatch.setattr(
        location_module, "get_location_provider", lambda: FakeGeocodeProvider()
    )


def _result(title: str, url: str, description: str, published: datetime | None = None) -> WebSearchResult:
    return WebSearchResult(
        id=f"id-{url}",
        title=title,
        url=url,
        domain=url.split("/")[2],
        description=description,
        page_fetched=published,
        provider="fake-search",
    )


@pytest.fixture(autouse=True)
def _enable_research(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_RESEARCH_ENABLED", True)
    monkeypatch.setattr(settings, "MARKET_RESEARCH_AI_SUMMARY", False)


def _service(provider, db=None) -> ExternalMarketService:
    return ExternalMarketService(db or FakeDB(), provider_factory=lambda: provider)


# ─── observations come only from retrieved text ────────────────────────────

def test_observations_are_extracted_with_sources():
    published = datetime.now(timezone.utc) - timedelta(days=2)
    provider = FakeSearchProvider([
        _result(
            "Property rates in Nandyal 2026",
            "https://example.com/rates",
            "Average asking price is Rs 7,500 per sq ft; 2 BHK flats start at Rs 45,00,000.",
            published,
        ),
        _result(
            "Nandyal rents",
            "https://example.org/rents",
            "Monthly rent for a 2 BHK is Rs 12,000/month in Nandyal.",
        ),
    ])
    service = _service(provider)
    research = service.research(MarketResearchFilter(location="Nandyal"), use_cache=False)

    assert research["status"] == "ok"
    kinds = {o["kind"] for o in research["observations"]}
    assert "asking_price" in kinds
    assert "price_per_sqft" in kinds
    assert "rent" in kinds
    # Every observation carries a clickable source + timestamps.
    for obs in research["observations"]:
        assert obs["source"]["url"].startswith("http")
        assert obs["source"]["retrieved_at"]
    # Publication date is preserved when the provider reported one.
    dated = [o for o in research["observations"] if o["source"]["published_at"]]
    assert dated and dated[0]["source"]["published_at"].startswith("20")
    # Statistics are computed from the observations, never invented.
    asking = research["statistics"]["asking_price"]
    assert asking["available"] is True
    assert asking["sample_size"] == 1
    assert asking["median"] == 4500000.0
    psf = research["statistics"]["price_per_sqft"]
    assert psf["median"] == 7500.0
    rent = research["statistics"]["rent_monthly"]
    assert rent["median"] == 12000.0


def test_rental_yield_only_when_both_price_and_rent_exist():
    provider = FakeSearchProvider([
        _result("Rates", "https://a.example/1", "Rs 50,00,000 for sale; rent is Rs 15,000/month."),
    ])
    research = _service(provider).research(MarketResearchFilter(location="X"), use_cache=False)
    yield_stats = research["statistics"]["rental_yield"]
    assert yield_stats["gross_rental_yield_pct"] == pytest.approx(3.6, abs=0.01)
    # Net yield requires expense inputs → never fabricated.
    assert yield_stats["net_rental_yield_pct"] is None


def test_rental_yield_is_absent_without_a_price():
    provider = FakeSearchProvider([
        _result("Rents", "https://a.example/1", "Rent is Rs 15,000/month nearby."),
    ])
    research = _service(provider).research(MarketResearchFilter(location="X"), use_cache=False)
    assert research["statistics"]["rental_yield"]["gross_rental_yield_pct"] is None


def test_small_samples_are_not_reported_as_measured():
    provider = FakeSearchProvider([
        _result("Rates", "https://a.example/1", "Rs 60,00,000 for sale in town centre."),
    ])
    research = _service(provider).research(MarketResearchFilter(location="X"), use_cache=False)
    asking = research["statistics"]["asking_price"]
    assert asking["available"] is True
    assert asking["is_measured"] is False


# ─── typed failure states (never fabricated data) ──────────────────────────

def test_unconfigured_provider_reports_not_configured():
    def boom():
        raise WebSearchNotConfiguredError("no provider configured")

    research = ExternalMarketService(FakeDB(), provider_factory=boom).research(
        MarketResearchFilter(location="Hyderabad"), use_cache=False
    )
    assert research["status"] == "not_configured"
    assert research["observations"] == []
    assert research["statistics"] == {}


def test_provider_failure_reports_unavailable():
    research = _service(FailingSearchProvider()).research(
        MarketResearchFilter(location="Hyderabad"), use_cache=False
    )
    assert research["status"] == "unavailable"
    assert research["observations"] == []


def test_no_usable_figures_reports_no_results():
    provider = FakeSearchProvider([
        _result("Local news", "https://a.example/1", "The town celebrated its annual festival."),
    ])
    research = _service(provider).research(MarketResearchFilter(location="X"), use_cache=False)
    assert research["status"] == "no_results"


def test_disabled_feature_reports_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_RESEARCH_ENABLED", False)
    research = _service(FakeSearchProvider([])).research(MarketResearchFilter(location="X"))
    assert research["status"] == "not_configured"


# ─── cache behaviour ───────────────────────────────────────────────────────

def test_repeat_query_is_served_from_cache():
    provider = FakeSearchProvider([
        _result("Rates", "https://a.example/1", "Rs 7,000 per sq ft in this area."),
    ])
    service = _service(provider)
    flt = MarketResearchFilter(location="Nandyal")
    first = service.research(flt)
    second = service.research(flt)
    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True
    assert len(provider.calls) == len(first["queries_used"])  # only the first run searched


def test_cache_key_differs_for_filters_and_location():
    service = _service(FakeSearchProvider([]))
    base = MarketResearchFilter(location="Nandyal")
    other_rent = MarketResearchFilter(location="Nandyal", listing_type="rent")
    other_city = MarketResearchFilter(location="Hyderabad")
    k1 = service._cache and __import__("app.core.cache", fromlist=["cache_key"]).cache_key(
        "market_research", base.normalized())
    k2 = __import__("app.core.cache", fromlist=["cache_key"]).cache_key(
        "market_research", other_rent.normalized())
    k3 = __import__("app.core.cache", fromlist=["cache_key"]).cache_key(
        "market_research", other_city.normalized())
    assert len({k1, k2, k3}) == 3


def test_expired_cache_triggers_refresh():
    from datetime import datetime as _dt

    provider = FakeSearchProvider([
        _result("Rates", "https://a.example/1", "Rs 7,000 per sq ft in this area."),
    ])
    service = _service(provider)
    flt = MarketResearchFilter(location="Nandyal")
    service.research(flt)
    calls_after_first = len(provider.calls)
    # Expire every market_research entry.
    for doc in service._cache.coll._docs:
        if doc["key"].startswith("market_research:"):
            doc["expires_at"] = _dt.now(timezone.utc) - timedelta(seconds=10)
    service.research(flt)
    assert len(provider.calls) > calls_after_first


# ─── AI summary validation ────────────────────────────────────────────────

def test_ai_summary_is_rejected_when_it_invents_a_number(monkeypatch):
    provider = FakeSearchProvider([
        _result("Rates", "https://a.example/1", "Rs 7,500 per sq ft on average in this market."),
    ])

    class FakeGateway:
        def chat(self, messages, tools, **kwargs):
            class R:
                class message:
                    content = "Prices average $9,999 per sq ft here, which is a bargain."
                model = "fake-model"
                provider = "fake-provider"
            return R()

    monkeypatch.setattr(settings, "MARKET_RESEARCH_AI_SUMMARY", True)
    import app.ai.gateway as gateway_module

    monkeypatch.setattr(gateway_module, "get_gateway", lambda: FakeGateway())
    research = _service(provider).research(MarketResearchFilter(location="X"), use_cache=False)
    # The fabricated number must cause the summary to be dropped entirely.
    assert research["ai_summary"] is None


def test_ai_summary_is_kept_when_every_number_is_evidenced(monkeypatch):
    provider = FakeSearchProvider([
        _result("Rates", "https://a.example/1", "Rs 7,500 per sq ft on average in this market."),
    ])

    class FakeGateway:
        def chat(self, messages, tools, **kwargs):
            class R:
                class message:
                    content = "Retrieved sources report about Rs 7,500 per sq ft for this market."
                model = "fake-model"
                provider = "fake-provider"
            return R()

    monkeypatch.setattr(settings, "MARKET_RESEARCH_AI_SUMMARY", True)
    import app.ai.gateway as gateway_module

    monkeypatch.setattr(gateway_module, "get_gateway", lambda: FakeGateway())
    research = _service(provider).research(MarketResearchFilter(location="X"), use_cache=False)
    summary = research["ai_summary"]
    assert summary is not None
    assert "7,500" in summary["text"]
    assert summary["label"].startswith("AI summary of retrieved external observations")


def test_ai_failure_never_breaks_research(monkeypatch):
    provider = FakeSearchProvider([
        _result("Rates", "https://a.example/1", "Rs 7,500 per sq ft on average."),
    ])

    class BoomGateway:
        def chat(self, *a, **k):
            raise RuntimeError("provider down")

    monkeypatch.setattr(settings, "MARKET_RESEARCH_AI_SUMMARY", True)
    import app.ai.gateway as gateway_module

    monkeypatch.setattr(gateway_module, "get_gateway", lambda: BoomGateway())
    research = _service(provider).research(MarketResearchFilter(location="X"), use_cache=False)
    assert research["status"] == "ok"
    assert research["ai_summary"] is None
