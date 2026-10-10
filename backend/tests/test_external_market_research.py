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


# ─── data quality: per-sqft rates must not become asking prices ────────────

def test_per_sqft_rates_are_not_counted_as_asking_prices():
    """The exact production bug: "₹8,211 per square foot" is a rate, not a price."""
    from app.services.external_market_service import _extract_amounts

    text = (
        "Average property prices reached approximately Rs 8,211 per square foot. "
        "A 2 BHK flat typically costs Rs 75,00,000. Monthly rent is Rs 25,000/month."
    )
    found = _extract_amounts(text)
    asking = [a.value for a in found if a.kind == "asking_price"]
    psf = [a.value for a in found if a.kind == "price_per_sqft"]
    rent = [a.value for a in found if a.kind == "rent"]
    print("asking:", asking, "psf:", psf, "rent:", rent)
    # The per-sqft figure must appear ONLY as a psf rate.
    assert 8211.0 not in asking
    assert 8211.0 in psf
    # The real property price and rent are still captured.
    assert 7500000.0 in asking
    assert 25000.0 in rent


def test_small_amounts_near_price_words_are_rejected():
    """A price keyword must not launder a rate into an asking price."""
    from app.services.external_market_service import _extract_amounts

    for text in [
        "Property price starts at Rs 7,000 per sq ft here.",
        "The average price is Rs 32,000 per sq ft in this locality.",
        "Rent price from Rs 12,000/month.",
    ]:
        asking = [a.value for a in _extract_amounts(text) if a.kind == "asking_price"]
        assert asking == [], f"{text!r} produced asking prices {asking}"


def test_nightly_vacation_rates_are_excluded():
    """KAYAK-style "$10/night" holiday lets are not residential market data."""
    from app.services.external_market_service import _extract_amounts

    text = "Hyderabad Vacation Rentals from $10/night on KAYAK."
    found = _extract_amounts(text)
    rents = [a for a in found if a.kind == "rent"]
    assert all(a.unit != "per_night" for a in found)
    assert all(a.unit == "per_month" for a in rents)


def test_implausible_project_totals_are_rejected():
    """A ₹45.99 billion figure is a portfolio total, not a property price."""
    from app.services.external_market_service import _extract_amounts

    found = _extract_amounts("Total project value Rs 45,990 Cr for the township.")
    asking = [a.value for a in found if a.kind == "asking_price"]
    assert 459900000000.0 not in asking


def test_currency_bounds_are_applied():
    from app.services.external_market_service import _extract_amounts

    # $15 is below the USD property floor -> not an asking price.
    assert not [a for a in _extract_amounts("Home listed at $15 today.") if a.kind == "asking_price"]
    # $350,000 is a plausible US property.
    assert [a for a in _extract_amounts("Home listed at $350,000 today.") if a.kind == "asking_price"]


def test_statistics_are_computed_per_currency_not_blended():
    """A median across ₹ and $ values is meaningless; they must not be blended."""
    from app.services.external_market_service import ExternalMarketService, Observation

    service = _service(FakeSearchProvider([]))
    observations = [
        Observation("asking_price", 1_000_000.0, "INR"),
        Observation("asking_price", 1_100_000.0, "INR"),
        Observation("asking_price", 1_200_000.0, "INR"),
        # One tiny USD figure must not drag the INR median down.
        Observation("asking_price", 15.0, "USD"),
    ]
    stats = service._statistics(observations, MarketResearchFilter(location="X"))
    assert stats["asking_price"]["currency"] == "INR"
    assert stats["asking_price"]["median"] == 1_100_000.0
    assert stats["asking_price"]["excluded_other_currencies"] == 1


def test_implausible_yield_is_reported_as_unavailable():
    """The 1383% bug: pairing a psf figure with a rent must not yield a number."""
    from app.services.external_market_service import ExternalMarketService, Observation

    service = _service(FakeSearchProvider([]))
    observations = [
        # Asking median lands on a per-sqft-scale figure.
        Observation("asking_price", 32_000.0, "INR"),
        Observation("asking_price", 33_000.0, "INR"),
        Observation("asking_price", 31_000.0, "INR"),
        Observation("rent", 36_899.0, "INR", "per_month"),
        Observation("rent", 37_000.0, "INR", "per_month"),
        Observation("rent", 35_000.0, "INR", "per_month"),
    ]
    stats = service._statistics(observations, MarketResearchFilter(location="X"))
    assert stats["rental_yield"]["gross_rental_yield_pct"] is None
    assert stats["rental_yield"]["reason"]
    assert "plausible" in stats["rental_yield"]["reason"]


def test_plausible_yield_is_still_reported():
    from app.services.external_market_service import ExternalMarketService, Observation

    service = _service(FakeSearchProvider([]))
    observations = [
        Observation("asking_price", 5_000_000.0, "INR"),
        Observation("asking_price", 5_200_000.0, "INR"),
        Observation("asking_price", 4_800_000.0, "INR"),
        Observation("rent", 20_000.0, "INR", "per_month"),
        Observation("rent", 21_000.0, "INR", "per_month"),
        Observation("rent", 19_000.0, "INR", "per_month"),
    ]
    stats = service._statistics(observations, MarketResearchFilter(location="X"))
    assert stats["rental_yield"]["gross_rental_yield_pct"] == pytest.approx(4.8, abs=0.1)


def test_yield_is_not_computed_across_currencies():
    from app.services.external_market_service import ExternalMarketService, Observation

    service = _service(FakeSearchProvider([]))
    observations = [
        Observation("asking_price", 5_000_000.0, "INR"),
        Observation("asking_price", 5_200_000.0, "INR"),
        Observation("asking_price", 4_800_000.0, "INR"),
        Observation("rent", 2_000.0, "USD", "per_month"),
        Observation("rent", 2_100.0, "USD", "per_month"),
        Observation("rent", 1_900.0, "USD", "per_month"),
    ]
    stats = service._statistics(observations, MarketResearchFilter(location="X"))
    assert stats["rental_yield"]["gross_rental_yield_pct"] is None
    assert "different currencies" in stats["rental_yield"]["reason"]


def test_end_to_end_extraction_produces_sane_asking_price():
    """The full pipeline on realistic page text must give a property-scale median."""
    from app.services.external_market_service import ExternalMarketService, Observation

    service = _service(FakeSearchProvider([
        _result(
            "Property rates in Hyderabad",
            "https://a.example/rates",
            "Average price is Rs 8,211 per square foot. 2 BHK flats start at Rs 85,00,000.",
        ),
        _result(
            "Hyderabad rents",
            "https://b.example/rents",
            "Monthly rent for a 2 BHK is Rs 28,000/month in Gachibowli.",
        ),
        _result(
            "Hyderabad market trends",
            "https://c.example/trends",
            "Apartments range from Rs 65,00,000 to Rs 1.4 Cr. Prices have risen this year.",
        ),
    ]))
    research = service.research(MarketResearchFilter(location="Hyderabad"), use_cache=False)
    asking = research["statistics"]["asking_price"]
    assert asking["available"] is True
    # Median must be a property-scale figure, not a per-sqft rate.
    assert asking["median"] >= 500_000, f"asking median {asking['median']} looks like a rate"
    assert 8211.0 not in [o["value"] for o in research["observations"] if o["kind"] == "asking_price"]
    assert research["statistics"]["price_per_sqft"]["median"] == 8211.0
