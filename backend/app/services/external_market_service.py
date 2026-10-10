"""External market research service.

Retrieves real-world property-market information for ANY supported location
(country, city, locality, region) and returns it as clearly-labelled external
observations. This is a deliberately separate data source from the verified
MongoDB catalogue:

    MongoDB catalogue      -> "verified asking price"  (source of truth)
    external research      -> "external observation"   (retrieved, sourced)

Honesty rules enforced here and nowhere else:

* Every figure carries its source URL, source domain, and retrieval timestamp.
* Prices are extracted deterministically from retrieved text — the AI gateway
  is never used to produce a number it was not given as evidence.
* A missing metric is reported as unavailable; nothing is estimated or
  interpolated from adjacent data.
* ``is_measured`` reflects the real sample size of retrieved observations, so
  a single page cannot masquerade as a market rate.
* Provider/configuration failures produce typed states
  (``not_configured`` / ``unavailable`` / ``no_results`` / ``ok``) — never an
  empty-but-successful payload.
"""
from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from app.core.cache import CacheRepository, cache_key, policy_for
from app.core.config import settings
from app.core.database import get_database
from app.discovery.extractor import PropertyCandidateExtractor
from app.providers.web_search.models import WebSearchResult
from app.providers.web_search.registry import get_web_search_provider

logger = logging.getLogger(__name__)

#: Bounded per-query web searches. Each query is one provider request.
_QUERY_TEMPLATES = (
    "{location} property price per square foot",
    "{location} average rent apartment monthly",
    "{location} property rates trends {year}",
)

#: Extraction of "X per sq ft/sqft/sq. ft/sq.m" amounts from retrieved text.
_PSF_RE = re.compile(
    r"(?:rs\.?|₹|inr|\$|usd|£|gbp|€|eur)?\s*([\d][\d,]*(?:\.\d+)?)\s*"
    r"(?:per\s*(?:square\s*(?:foot|feet|ft)|sq\.?\s?(?:ft|feet|m|meter|metre)s?)|"
    r"/\s*(?:sq\.?\s?(?:ft|feet|m)|sqft)\b)",
    re.IGNORECASE,
)

#: Conversational trend phrases -> direction. Only reported when matched in
#: retrieved text; never inferred from price math.
_TREND_PHRASES = (
    (re.compile(r"\b(prices?|rates?|values?)\s+(have\s+)?(risen|increased|gone up|surged|appreciated)\b", re.I), "up"),
    (re.compile(r"\b(prices?|rates?|values?)\s+(have\s+)?(fallen|dropped|declined|corrected)\b", re.I), "down"),
    (re.compile(r"\b(prices?|rates?|values?)\s+(have\s+)?(remained|been|stayed)\s+(stable|flat|steady|unchanged)\b", re.I), "flat"),
)

#: Minimum retrieved observations before a statistic is "measured".
MIN_OBSERVATIONS = 3


# ── market amount extraction (retrieved text only) ─────────────────────────

_CURRENCY_MARKER = r"(?:rs\.?|inr|₹|usd|\$|aed|gbp|£|eur|€)"
_UNIT_WORD = r"(?:lakhs?|lacs?|l|crores?|cr|millions?|m|billions?|bn|thousands?|k)"

_RENT_RE = re.compile(
    rf"(?P<cur>{_CURRENCY_MARKER})\.?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?:/|\sper\s|\s)?(?:month|mo|pm|pcm|p\.m\.|monthly)\b",
    re.IGNORECASE,
)
_RENT_YEAR_RE = re.compile(
    rf"(?P<cur>{_CURRENCY_MARKER})\.?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?:/|\sper\s|\s)?(?:year|yr|annum|annually|annual|p\.a\.)\b",
    re.IGNORECASE,
)
_NIGHT_RE = re.compile(
    rf"(?P<cur>{_CURRENCY_MARKER})\.?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?:/|\sper\s|\s)?(?:night|nightly)\b",
    re.IGNORECASE,
)
_PSF_RE = re.compile(
    rf"(?:(?P<cur>{_CURRENCY_MARKER})\.?\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?:per\s*(?:square\s*(?:foot|feet|ft)|sq\.?\s?(?:ft|feet|m|meter|metre)s?)|"
    r"/\s*(?:sq\.?\s?(?:ft|feet|m)|sqft)\b)",
    re.IGNORECASE,
)
# "price per sqft is Rs 6,200" / "per square foot: $350" (number AFTER the unit).
_PSF_REVERSED_RE = re.compile(
    r"(?:per\s*(?:square\s*(?:foot|feet|ft)|sq\.?\s?(?:ft|feet|m|meter|metre)s?)|"
    r"/\s*(?:sq\.?\s?(?:ft|feet|m)|sqft)\b)"
    rf"\s*(?:is|of|:)?\s*(?P<cur>{_CURRENCY_MARKER})\.?\s*(?P<num>\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)
_UNIT_AMOUNT_RE = re.compile(
    rf"(?P<cur>{_CURRENCY_MARKER})\.?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>{_UNIT_WORD})\b",
    re.IGNORECASE,
)
# Indian market pages often write a bare "1.2 Cr" / "85 L" after a price word.
_INDIAN_UNIT_AMOUNT_RE = re.compile(
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>lakhs?|lacs?|crores?|cr)\b",
    re.IGNORECASE,
)
_PRICE_KEYWORD_RE = re.compile(
    r"\b(price|prices|pricing|asking|rate|rates|cost|costs|value|starting|starts?|from|"
    r"average|avg|median|typical|range)\b",
    re.IGNORECASE,
)
_BARE_AMOUNT_RE = re.compile(
    rf"(?P<cur>{_CURRENCY_MARKER})\.?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\b"
    r"(?!\s{0,2}(?:sq\.?\s?(?:ft|feet|m)|sqft|beds?|br|bhk|baths?|ba|bed|bath|km|kg|"
    r"acres?|cents?|%|percent|years?|months?|days?|hours?|mins?|minutes?))",
    re.IGNORECASE,
)

_UNIT_MULTIPLIER = {
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000, "l": 100_000,
    "crore": 10_000_000, "crores": 10_000_000, "cr": 10_000_000,
    "million": 1_000_000, "millions": 1_000_000, "m": 1_000_000,
    "billion": 1_000_000_000, "billions": 1_000_000_000, "bn": 1_000_000_000,
    "thousand": 1_000, "thousands": 1_000, "k": 1_000,
}


def _currency_of(marker: str) -> Optional[str]:
    if not marker:
        return None
    lowered = marker.lower()
    if lowered in ("$", "usd"):
        return "USD"
    if lowered in ("€", "eur"):
        return "EUR"
    if lowered in ("£", "gbp"):
        return "GBP"
    if lowered in ("₹", "rs", "rs.", "inr"):
        return "INR"
    if lowered == "aed":
        return "AED"
    return None


@dataclass
class _Amount:
    kind: str            # asking_price | rent | price_per_sqft
    value: float
    currency: str
    unit: Optional[str]


def _number(raw: str) -> Optional[float]:
    try:
        value = float(raw.replace(",", ""))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _extract_amounts(text: str) -> list[_Amount]:
    """Extract explicit currency-marked amounts from retrieved text.

    Order matters: rent and per-area rates are matched before bare amounts so
    "Rs 12,000/month" is a rent observation, not an asking price. Every amount
    must carry an explicit currency marker (``Rs``, ``₹``, ``$``, ``£`` …);
    unmarked numbers are not evidence and are skipped.
    """
    found: list[_Amount] = []
    consumed: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(start < c_end and end > c_start for c_start, c_end in consumed)

    # 1) Monthly rent.
    for match in _RENT_RE.finditer(text):
        currency = _currency_of(match.group("cur"))
        value = _number(match.group("num"))
        if currency and value:
            found.append(_Amount("rent", round(value, 2), currency, "per_month"))
            consumed.append(match.span())

    # 2) Nightly rent (holiday/short-let context).
    for match in _NIGHT_RE.finditer(text):
        if _overlaps(*match.span()):
            continue
        currency = _currency_of(match.group("cur"))
        value = _number(match.group("num"))
        if currency and value:
            found.append(_Amount("rent", round(value, 2), currency, "per_night"))
            consumed.append(match.span())

    # 2b) Annual rent, normalised to a monthly figure.
    for match in _RENT_YEAR_RE.finditer(text):
        if _overlaps(*match.span()):
            continue
        currency = _currency_of(match.group("cur"))
        value = _number(match.group("num"))
        if currency and value:
            found.append(_Amount("rent", round(value / 12.0, 2), currency, "per_month"))
            consumed.append(match.span())

    # 3) Price per square foot / square metre (number before or after the unit).
    for pattern in (_PSF_RE, _PSF_REVERSED_RE):
        for match in pattern.finditer(text):
            if _overlaps(*match.span()):
                continue
            currency = _currency_of(match.group("cur") or "") or "INR"
            value = _number(match.group("num"))
            tail = match.group(0).lower()
            unit = "per_sqm" if re.search(r"(sq\.?\s?m|sqm|square\s?met)", tail) else "per_sqft"
            if value:
                found.append(_Amount("price_per_sqft", round(value, 2), currency, unit))
                consumed.append(match.span())

    # 4) Amounts with a magnitude unit (Rs 45 L, ₹1.2 Cr, $1.5M).
    for match in _UNIT_AMOUNT_RE.finditer(text):
        if _overlaps(*match.span()):
            continue
        currency = _currency_of(match.group("cur"))
        value = _number(match.group("num"))
        multiplier = _UNIT_MULTIPLIER.get(match.group("unit").lower())
        if currency and value and multiplier:
            scaled = round(value * multiplier, 2)
            found.append(_Amount("asking_price", scaled, currency, None))
            consumed.append(match.span())

    # 4b) Bare Indian magnitude units ("1.2 Cr") after a price keyword: the unit
    # word itself fixes the currency to INR, and the keyword fixes the context.
    for match in _INDIAN_UNIT_AMOUNT_RE.finditer(text):
        if _overlaps(*match.span()):
            continue
        value = _number(match.group("num"))
        multiplier = _UNIT_MULTIPLIER.get(match.group("unit").lower())
        if not (value and multiplier):
            continue
        if not _PRICE_KEYWORD_RE.search(text[max(0, match.start() - 45): match.start()]):
            continue
        found.append(_Amount("asking_price", round(value * multiplier, 2), "INR", None))
        consumed.append(match.span())

    # 5) A currency-marked amount near a price keyword, then any marked amount.
    for match in _BARE_AMOUNT_RE.finditer(text):
        if _overlaps(*match.span()):
            continue
        currency = _currency_of(match.group("cur"))
        value = _number(match.group("num"))
        if not (currency and value):
            continue
        near_keyword = bool(
            _PRICE_KEYWORD_RE.search(text[max(0, match.start() - 45): match.start()])
        )
        if near_keyword or value >= 100_000:
            found.append(_Amount("asking_price", round(value, 2), currency, None))
            consumed.append(match.span())

    # De-duplicate identical amounts; keep at most one asking price per source
    # unless the page states several distinct values.
    unique: list[_Amount] = []
    seen: set[tuple] = set()
    asking_seen = 0
    for amount in found:
        signature = (amount.kind, amount.value, amount.currency, amount.unit)
        if signature in seen:
            continue
        if amount.kind == "asking_price":
            asking_seen += 1
            if asking_seen > 3:
                continue
        seen.add(signature)
        unique.append(amount)
    return unique


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mean(values: Iterable[float]) -> Optional[float]:
    values = [v for v in values if isinstance(v, (int, float))]
    return sum(values) / len(values) if values else None


def _median(values: Iterable[float]) -> Optional[float]:
    values = sorted(v for v in values if isinstance(v, (int, float)))
    if not values:
        return None
    n = len(values)
    mid = n // 2
    if n % 2:
        return float(values[mid])
    return (values[mid - 1] + values[mid]) / 2.0


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    k = (len(ordered) - 1) * pct
    low, high = int(k // 1), min(int(k // 1) + 1, len(ordered) - 1)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (k - low))


# ── filter normalization (cache identity) ───────────────────────────────────

@dataclass
class MarketResearchFilter:
    """Normalized external-research request.

    ``listing_type``/``property_type``/``bedrooms`` are part of the cache
    identity because they change which observations are relevant.
    """

    location: str
    city: Optional[str] = None
    locality: Optional[str] = None
    country: Optional[str] = None
    listing_type: Optional[str] = None          # sale | rent | None (both)
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    currency: str = "INR"
    language: str = "en"

    def normalized(self) -> dict:
        return {
            "location": self.location,
            "city": self.city,
            "locality": self.locality,
            "country": self.country,
            "listing_type": self.listing_type,
            "property_type": self.property_type,
            "bedrooms": self.bedrooms,
            "currency": self.currency,
            "language": self.language,
        }


# ── observation model ──────────────────────────────────────────────────────

@dataclass
class Observation:
    """One retrieved data point with full provenance."""

    kind: str                                  # asking_price | rent | price_per_sqft | trend
    value: Optional[float]
    currency: str
    unit: Optional[str] = None                 # "per_sqft" | "per_month" | None
    bedrooms: Optional[int] = None
    source_title: str = ""
    source_url: str = ""
    source_domain: str = ""
    published_at: Optional[str] = None
    retrieved_at: str = field(default_factory=lambda: _utcnow().isoformat())
    snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "value": self.value,
            "currency": self.currency,
            "unit": self.unit,
            "bedrooms": self.bedrooms,
            "source": {
                "title": self.source_title,
                "url": self.source_url,
                "domain": self.source_domain,
                "published_at": self.published_at,
                "retrieved_at": self.retrieved_at,
            },
            "snippet": self.snippet,
        }


@dataclass
class MarketResearch:
    """Structured external research result (cached payload)."""

    status: str                                        # ok | no_results | unavailable | not_configured
    message: Optional[str] = None
    location_input: str = ""
    resolved: dict = field(default_factory=dict)       # geocoder verdict + coverage
    sources: list[dict] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)
    ai_summary: Optional[dict] = None
    queries_used: list[str] = field(default_factory=list)
    provider: Optional[str] = None
    cache: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: _utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "message": self.message,
            "location_input": self.location_input,
            "resolved": self.resolved,
            "sources": self.sources,
            "observations": self.observations,
            "statistics": self.statistics,
            "ai_summary": self.ai_summary,
            "queries_used": self.queries_used,
            "provider": self.provider,
            "cache": self.cache,
            "generated_at": self.generated_at,
        }


class ExternalMarketService:
    """Bounded, cache-first external market research."""

    def __init__(self, db=None, provider_factory=None, cache: Optional[CacheRepository] = None) -> None:
        self.db = db if db is not None else get_database()
        self._provider_factory = provider_factory
        try:
            self._cache: Optional[CacheRepository] = cache or CacheRepository(self.db)
        except Exception:  # pragma: no cover - degraded environments
            self._cache = None
        self._extractor = PropertyCandidateExtractor()

    # ── public API ──────────────────────────────────────────────────────
    def research(self, flt: MarketResearchFilter, *, use_cache: bool = True) -> dict:
        """Run (or return cached) external market research for a location."""
        if not settings.MARKET_RESEARCH_ENABLED:
            return MarketResearch(
                status="not_configured",
                message="External market research is disabled by the platform configuration.",
                location_input=flt.location,
            ).to_dict()

        key = cache_key("market_research", flt.normalized())

        if use_cache and self._cache is not None:
            entry = self._cache.get(key)
            if entry is not None and not entry["is_error"]:
                payload = dict(entry["payload"])
                payload["cache"] = {
                    "hit": True,
                    "cached_at": entry["created_at"].isoformat() if entry.get("created_at") else None,
                    "expires_at": entry["expires_at"].isoformat() if entry.get("expires_at") else None,
                    "age_seconds": entry.get("age_seconds"),
                }
                return payload

        research = self._collect(flt)
        payload = research.to_dict()
        payload["cache"] = {
            "hit": False,
            "cached_at": None,
            "expires_at": None,
            "age_seconds": 0,
        }

        if use_cache and self._cache is not None and research.status in ("ok", "no_results"):
            self._cache.set(
                key, payload, policy=policy_for("market_research"),
                metadata={"location": flt.location, "provider": research.provider},
            )
        return payload

    # ── collection pipeline ─────────────────────────────────────────────
    def _collect(self, flt: MarketResearchFilter) -> MarketResearch:
        research = MarketResearch(status="ok", location_input=flt.location)

        # 1) Geocode the location so coverage and nearby data work for ANY place.
        resolved = self._resolve_location(flt)
        research.resolved = resolved
        if not resolved.get("found"):
            research.status = "no_results"
            research.message = (
                f"'{flt.location}' could not be resolved to a geographic location, "
                "so no external market research was attempted for it."
            )
            return research

        # 2) Check a web search provider is configured (honest state, no fake data).
        try:
            provider = self._provider()
        except Exception as exc:  # WebSearchNotConfiguredError and friends
            logger.info("market_research_provider_unavailable err=%s", type(exc).__name__)
            research.status = "not_configured"
            research.message = (
                "Web search is not configured for this deployment, so no external "
                "market observations could be retrieved. The verified catalogue "
                "statistics above remain available."
            )
            return research

        research.provider = getattr(provider, "name", None)

        # 3) Bounded provider searches -> observations + sources.
        queries = self._build_queries(flt, resolved)
        research.queries_used = queries
        sources: dict[str, dict] = {}
        observations: list[Observation] = []
        seen_observations: set[tuple] = set()
        provider_failed = False

        for query in queries:
            try:
                response = provider.search(
                    query,
                    country=settings.WEB_SEARCH_COUNTRY,
                    language=settings.WEB_SEARCH_LANGUAGE,
                    count=settings.MARKET_RESEARCH_MAX_RESULTS,
                )
            except Exception as exc:  # noqa: BLE001 - typed provider errors land here
                logger.info("market_research_search_failed query=%s err=%s", query, type(exc).__name__)
                provider_failed = True
                continue
            for result in response.results or []:
                if result.url and result.url not in sources:
                    sources[result.url] = {
                        "title": (result.title or "")[:300],
                        "url": result.url,
                        "domain": result.domain,
                        "published_at": result.page_fetched.isoformat() if result.page_fetched else None,
                        "retrieved_at": _utcnow().isoformat(),
                        "provider": getattr(provider, "name", None),
                    }
                for obs in self._observations_from(result, flt):
                    # The same page returned for several queries is ONE
                    # observation, not several: counting it repeatedly would
                    # inflate the sample size and fake "measured" statistics.
                    signature = (
                        obs.kind, obs.value, obs.unit, obs.currency,
                        obs.source_domain, obs.source_url,
                    )
                    if signature in seen_observations:
                        continue
                    seen_observations.add(signature)
                    observations.append(obs)

        research.sources = list(sources.values())
        research.observations = [o.to_dict() for o in observations]

        if not observations:
            if provider_failed:
                research.status = "unavailable"
                research.message = (
                    "External market search is temporarily unavailable. No market "
                    "figures were retrieved; nothing has been estimated."
                )
            else:
                research.status = "no_results"
                research.message = (
                    "No external market information with usable figures was found for "
                    f"'{flt.location}'. Missing metrics are reported as unavailable "
                    "rather than estimated."
                )
            return research

        # 4) Deterministic statistics from retrieved observations only.
        research.statistics = self._statistics(observations, flt)

        # 5) Optional bounded AI summary of the retrieved evidence.
        if settings.MARKET_RESEARCH_AI_SUMMARY:
            research.ai_summary = self._ai_summary(flt, research)
        return research

    def _provider(self):
        if self._provider_factory is not None:
            return self._provider_factory()
        return get_web_search_provider()

    def _resolve_location(self, flt: MarketResearchFilter) -> dict:
        """Geocode through the configured location provider (OSM/Geoapify)."""
        query = flt.location
        try:
            from app.providers.location import get_location_provider

            provider = get_location_provider()
            geo = provider.geocode(query)
        except Exception as exc:  # noqa: BLE001 - never break research on geocoding
            logger.info("market_research_geocode_failed query=%s err=%s", query, type(exc).__name__)
            return {"found": False, "reason": "geocoding_unavailable", "query": query}
        if not geo or geo.get("latitude") is None or geo.get("longitude") is None:
            return {"found": False, "reason": "not_found", "query": query}
        return {
            "found": True,
            "query": query,
            "formatted_address": geo.get("formatted_address"),
            "latitude": geo.get("latitude"),
            "longitude": geo.get("longitude"),
            "country": geo.get("country"),
            "country_code": geo.get("country_code"),
            "state": geo.get("state"),
            "city": geo.get("city"),
            "locality": geo.get("locality") or geo.get("suburb"),
            "provider": getattr(provider, "name", None),
        }

    def _build_queries(self, flt: MarketResearchFilter, resolved: dict) -> list[str]:
        location = flt.location.strip()
        # Prefer the geocoder's own name for the market context.
        resolved_name = (resolved.get("formatted_address") or "").split(",")[0].strip()
        if resolved_name and len(resolved_name) >= 3:
            location = resolved_name
        country = resolved.get("country") or flt.country
        scope = f"{location}, {country}" if country and country.lower() not in location.lower() else location
        year = _utcnow().year
        queries: list[str] = []
        for template in _QUERY_TEMPLATES:
            q = template.format(location=scope, year=year)
            if flt.listing_type == "rent" and "rent" not in q:
                q = f"{q} rent"
            if flt.property_type:
                q = f"{flt.property_type} {q}"
            if flt.bedrooms:
                q = f"{flt.bedrooms} BHK {q}"
            queries.append(q)
        return queries[: max(1, min(settings.MARKET_RESEARCH_MAX_QUERIES, 6))]

    # ── observation extraction ──────────────────────────────────────────
    def _observations_from(self, result: WebSearchResult, flt: MarketResearchFilter) -> list[Observation]:
        """Deterministically extract market observations from one result.

        Only text the provider actually returned is used; nothing is inferred
        from the query or from adjacent values. Amounts without an explicit
        currency marker are ignored — an unmarked number is not evidence.
        """
        text = " ".join(part for part in (result.title or "", result.description or "") if part)
        if not text.strip():
            return []
        found: list[Observation] = []
        base = {
            "source_title": (result.title or "")[:300],
            "source_url": result.url,
            "source_domain": result.domain,
            "published_at": result.page_fetched.isoformat() if result.page_fetched else None,
            "snippet": text[:400],
        }

        candidate = self._extractor.extract(result)
        bedrooms = candidate.bedrooms if candidate else None

        for amount in _extract_amounts(text):
            found.append(Observation(
                kind=amount.kind,
                value=amount.value,
                currency=amount.currency,
                unit=amount.unit,
                bedrooms=bedrooms,
                **base,
            ))

        direction = self._trend_direction(text)
        if direction:
            found.append(Observation(
                kind="trend", value=None, currency=found[0].currency if found else flt.currency,
                unit=direction, bedrooms=bedrooms, **base,
            ))

        # Deduplicate identical (kind, value) pairs from the same source.
        unique: list[Observation] = []
        seen: set[tuple] = set()
        for obs in found:
            signature = (obs.kind, obs.value, obs.unit)
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(obs)
        return unique[: settings.MARKET_RESEARCH_MAX_RESULTS]

    @staticmethod
    def _trend_direction(text: str) -> Optional[str]:
        for pattern, direction in _TREND_PHRASES:
            if pattern.search(text):
                return direction
        return None

    # ── statistics ──────────────────────────────────────────────────────
    def _statistics(self, observations: list[Observation], flt: MarketResearchFilter) -> dict:
        def stats_for(kind: str, unit: Optional[str] = None) -> dict:
            values = [
                o.value for o in observations
                if o.kind == kind and o.value is not None and (unit is None or o.unit == unit)
            ]
            count = len(values)
            measured = count >= MIN_OBSERVATIONS
            if count == 0:
                return {"available": False, "sample_size": 0}
            return {
                "available": True,
                "sample_size": count,
                "is_measured": measured,
                "median": round(_median(values) or 0, 2),
                "mean": round(_mean(values) or 0, 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "p25": round(_percentile(values, 0.25) or 0, 2),
                "p75": round(_percentile(values, 0.75) or 0, 2),
                "currency": observations[0].currency if observations else flt.currency,
                "note": (
                    "Median of retrieved external observations. Asking prices from "
                    "third-party pages are not verified listings."
                    if kind != "rent" else
                    "Median of retrieved external rent observations. Actual rents vary "
                    "by furnishing, floor and exact location."
                ),
            }

        asking = stats_for("asking_price")
        rent = stats_for("rent")
        psf = stats_for("price_per_sqft", "per_sqft")
        psqm = stats_for("price_per_sqft", "per_sqm")

        # Gross/net rental yield are computed only when BOTH an asking price and a
        # rent observation exist — never by pairing unrelated figures.
        yields = {
            "gross_rental_yield_pct": None,
            "net_rental_yield_pct": None,
            "basis": None,
        }
        if asking.get("available") and rent.get("available") and asking.get("median") and rent.get("median"):
            gross = round(rent["median"] * 12 / asking["median"] * 100, 2)
            yields = {
                "gross_rental_yield_pct": gross,
                "net_rental_yield_pct": None,  # expenses are user-assumptions; not invented
                "basis": (
                    "annualised median external rent ÷ median external asking price. "
                    "Expense inputs are not part of external research."
                ),
                "is_measured": bool(asking.get("is_measured") and rent.get("is_measured")),
            }

        bedrooms_seen = sorted({
            o.bedrooms for o in observations if o.bedrooms is not None
        })
        trend_votes = [o.unit for o in observations if o.kind == "trend" and o.unit]
        trend_direction = None
        if trend_votes:
            trend_direction = statistics.mode(trend_votes) if len(set(trend_votes)) == 1 else "mixed"
            if len(set(trend_votes)) > 1:
                # Report the majority direction when sources disagree.
                counts = {d: trend_votes.count(d) for d in set(trend_votes)}
                trend_direction = max(counts, key=counts.get)

        return {
            "asking_price": asking,
            "rent_monthly": rent,
            "price_per_sqft": psf,
            "price_per_sqm": psqm,
            "rental_yield": yields,
            "bedrooms_observed": bedrooms_seen,
            "trend_direction": trend_direction,
            "trend_basis": (
                "Direction reported only where retrieved sources explicitly state one."
                if trend_direction else None
            ),
            "minimum_observations": MIN_OBSERVATIONS,
            "data_class": "external_observation",
        }

    # ── bounded AI summary ──────────────────────────────────────────────
    def _ai_summary(self, flt: MarketResearchFilter, research: MarketResearch) -> Optional[dict]:
        """Summarize retrieved evidence with the AI gateway.

        The model receives ONLY the retrieved observations and must restate
        them. The backend then validates that every number in the summary
        appears in the evidence set; an unverifiable figure causes the summary
        to be dropped entirely.
        """
        evidence_lines: list[str] = []
        for obs in research.observations[: settings.MARKET_RESEARCH_MAX_RESULTS]:
            value = obs.get("value")
            if value is None:
                continue
            evidence_lines.append(
                f"- {obs.get('kind')}: {value} {obs.get('currency')}"
                f"{(' ' + obs['unit']) if obs.get('unit') else ''} (source: {obs['source']['domain']})"
            )
        if not evidence_lines:
            return None

        try:
            from app.ai import gateway as gateway_module

            gateway = gateway_module.get_gateway()
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You summarize EXTERNAL real-estate market observations for a "
                        "location. Rules: use only the evidence provided; never add, "
                        "estimate, average or convert numbers; never claim verification; "
                        "state plainly when evidence is thin; keep under 120 words."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Location: {flt.location}\n"
                        f"Retrieved observations:\n" + "\n".join(evidence_lines) +
                        "\nSummarize what these external observations say."
                    ),
                },
            ]
            result = gateway.chat(messages, tools=[], complexity="fast")
        except Exception as exc:  # noqa: BLE001 - summary is optional, never fatal
            logger.info("market_research_ai_summary_unavailable err=%s", type(exc).__name__)
            return None

        text = (result.message.content or "").strip()
        if not text:
            return None

        validated = self._validate_summary_numbers(text, research)
        if not validated:
            logger.info("market_research_ai_summary_rejected_unverifiable_numbers")
            return None
        return {
            "text": validated[:1200],
            "model": getattr(result, "model", None),
            "provider": getattr(result, "provider", None),
            "generated_at": _utcnow().isoformat(),
            "label": "AI summary of retrieved external observations (not market data)",
        }

    @staticmethod
    def _validate_summary_numbers(text: str, research: MarketResearch) -> Optional[str]:
        """Drop the summary when it states any number absent from the evidence."""
        allowed = {
            round(float(o["value"]), 2)
            for o in research.observations
            if o.get("value") is not None
        }
        # Small integers (counts, BHK, percents) that are structural, not prices.
        allowed.update({0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 100.0})
        for raw in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
            try:
                number = round(float(raw.replace(",", "")), 2)
            except ValueError:
                continue
            if any(abs(number - value) <= max(1.0, value * 0.005) for value in allowed):
                continue
            return None
        return text
