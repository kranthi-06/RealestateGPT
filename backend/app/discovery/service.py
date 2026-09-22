"""WebDiscoveryService: SearchIntent -> bounded provider searches ->
extraction -> deduplication -> ranking -> persistence -> bounded geocoding.

Failure semantics (Part 33 - NO FAKE FALLBACK):
* provider not configured -> WEB_SEARCH_NOT_CONFIGURED, zero fabricated results
* provider unavailable      -> WEB_SEARCH_UNAVAILABLE, zero fabricated results
* stale cache + fresh failure -> clearly-marked stale results allowed
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings
from app.discovery.cache import WebSearchCacheRepository, cache_key_for_intent
from app.discovery.deduplication import find_duplicates
from app.discovery.detector import PropertyListingDetector
from app.discovery.extractor import PropertyCandidateExtractor
from app.discovery.geocoding import DiscoveryGeocoder
from app.discovery.query_generation import build_search_queries
from app.discovery.ranking import score_candidate
from app.discovery.repository import WebDiscoveryRepository, to_doc
from app.providers.web_search.limiter import get_web_search_limiter
from app.providers.web_search.models import (
    WebSearchError,
    WebSearchNotConfiguredError,
    WebSearchRateLimitError,
    WebSearchResult,
)
from app.providers.web_search.registry import get_web_search_provider, web_search_health
from app.providers.web_search.security import is_allowed_domain
from app.schemas.ai import SearchIntent

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def freshness_label(discovered_at: Optional[datetime], page_fetched_at: Optional[datetime]) -> str:
    """Honest freshness wording. Never claims 'updated X ago' from discovery time."""
    reference = page_fetched_at or discovered_at
    if reference is None:
        return "Source page date unavailable"
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    seconds = max(0, int((_utcnow() - reference).total_seconds()))
    if page_fetched_at is not None:
        minutes = max(1, round(seconds / 60))
        return f"Source page fetched about {minutes} min ago"
    if seconds < 120:
        return "Discovered moments ago"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"Found {minutes} min ago"
    hours = round(minutes / 60)
    if hours < 24:
        return f"Discovered {hours} hr ago"
    days = round(hours / 24)
    return f"Discovered {days} days ago"

def doc_to_card(doc: dict[str, Any], *, saved: bool = False, rank_score: Optional[float] = None) -> dict[str, Any]:
    """Serialize a persisted discovery document into the API card shape."""
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title") or "Untitled listing",
        "url": doc.get("result_url") or "",
        "source_domain": doc.get("source_domain") or "",
        "source_name": doc.get("source_name"),
        "description": doc.get("description"),
        "price": doc.get("price"),
        "currency": doc.get("currency") or "INR",
        "transaction_type": doc.get("transaction_type"),
        "bedrooms": doc.get("bedrooms"),
        "bathrooms": doc.get("bathrooms"),
        "area": doc.get("area"),
        "area_unit": doc.get("area_unit"),
        "area_sqft": doc.get("area_sqft"),
        "location_text": doc.get("location_text"),
        "city": doc.get("city"),
        "locality": doc.get("locality"),
        "furnishing": doc.get("furnishing"),
        "image_url": doc.get("image_url"),
        "confidence": doc.get("confidence") or 0.0,
        "extraction_method": doc.get("extraction_method") or "snippet",
        "provider": doc.get("provider") or "web",
        "discovered_at": doc.get("discovered_at") or _utcnow(),
        "page_fetched_at": doc.get("page_fetched_at"),
        "page_age": doc.get("page_age"),
        "freshness_label": freshness_label(doc.get("discovered_at"), doc.get("page_fetched_at")),
        "latitude": doc.get("latitude"),
        "longitude": doc.get("longitude"),
        "rank_score": rank_score,
        "saved": saved,
        "verification_status": "web_discovery",
    }


@dataclass
class WebDiscoveryOutcome:
    status: str = "unavailable"       # available | disabled | not_configured | unavailable
    code: str = "WEB_SEARCH_UNAVAILABLE"
    message: Optional[str] = None
    cards: list[dict[str, Any]] = field(default_factory=list)
    queries_used: list[str] = field(default_factory=list)
    provider: Optional[str] = None
    cache_hit: bool = False
    stale_cache_used: bool = False
    duration_ms: float = 0.0
    inserted: int = 0
    sources_searched: list[str] = field(default_factory=list)


class WebDiscoveryService:
    """Bounded, cache-first web property discovery pipeline."""

    def __init__(self, db, provider_factory=None) -> None:
        self.db = db
        self.cache = WebSearchCacheRepository(db)
        self.repository = WebDiscoveryRepository(db)
        self.extractor = PropertyCandidateExtractor()
        self._provider_factory = provider_factory or (lambda: get_web_search_provider())
        self._limiter = get_web_search_limiter()
        self._health = web_search_health()

    def discover(
        self,
        intent: SearchIntent,
        *,
        user_key: str = "anonymous",
        queries: Optional[list[str]] = None,
        max_queries: Optional[int] = None,
        max_results: Optional[int] = None,
        enrich: bool = True,
        saved_ids: Optional[set[str]] = None,
    ) -> WebDiscoveryOutcome:
        started = time.perf_counter()
        max_queries = max_queries or settings.WEB_SEARCH_MAX_QUERIES

        if not settings.WEB_DISCOVERY_ENABLED:
            return WebDiscoveryOutcome(
                status="disabled", code="WEB_DISCOVERY_DISABLED",
                message="Web discovery is disabled by the platform configuration.",
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )

        try:
            provider = self._provider_factory()
        except WebSearchNotConfiguredError as exc:
            return WebDiscoveryOutcome(
                status="not_configured", code=exc.code, message=exc.message,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )

        cache_key = cache_key_for_intent(intent.model_dump())

        from app.discovery.sources import select_sources

        routed_sources = select_sources(intent, limit=settings.WEB_DISCOVERY_MAX_SOURCES)
        cached = self.cache.get(cache_key)
        if cached is not None:
            self._health.record_cache(True)
            cards = self._cards_from_cached(cached.get("results", []), intent, saved_ids)
            return WebDiscoveryOutcome(
                status="available", code="OK", message=None, cards=cards,
                queries_used=[cached.get("query") or ""], provider=cached.get("provider"),
                cache_hit=True, duration_ms=round((time.perf_counter() - started) * 1000, 1),
                sources_searched=[s.name for s in routed_sources],
            )
        self._health.record_cache(False)

        query_list = queries or build_search_queries(intent, max_queries)
        query_list = query_list[: max(1, min(int(max_queries), 5))]

        try:
            provider_response = self._run_queries(provider, query_list, max_results)
        except WebSearchError as exc:
            stale = self.cache.get_stale(cache_key)
            message = exc.message
            if stale is not None:
                self._health.record_error(exc.code)
                logger.warning("web_search_stale_fallback query_hash=%s error=%s", cache_key, exc.code)
                return WebDiscoveryOutcome(
                    status="available", code="WEB_SEARCH_STALE",
                    message="Previously discovered results — freshness not verified. " + message,
                    cards=self._cards_from_cached(stale.get("results", []), intent, saved_ids),
                    queries_used=query_list, provider=provider.name,
                    stale_cache_used=True,
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                )
            self._health.record_error(exc.code)
            return WebDiscoveryOutcome(
                status="unavailable", code=exc.code, message=message,
                queries_used=query_list, provider=provider.name,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
        except Exception as exc:  # noqa: BLE001 - unexpected provider-layer failure
            self._health.record_error(type(exc).__name__)
            logger.exception("web_search_unexpected query_hash=%s", cache_key)
            return WebDiscoveryOutcome(
                status="unavailable", code="WEB_SEARCH_UNAVAILABLE",
                message="Web discovery is temporarily unavailable.",
                queries_used=query_list, provider=provider.name,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )

        # Listing detection + conservative validation before anything is stored.
        detector = PropertyListingDetector()
        from app.discovery.validation import validate_candidate

        candidates: list[Any] = []
        for query, result in provider_response["items"]:
            candidate = self.extractor.extract(result, intent_city=intent.city)
            if candidate is None:
                continue
            candidate.query = query
            candidates.append(candidate)
        if settings.web_search_allowed_domains:
            candidates = [
                c for c in candidates
                if is_allowed_domain(c.source_domain, settings.web_search_allowed_domains)
            ]

        filtered: list[Any] = []
        for candidate in candidates:
            detection = detector.detect(candidate, intent)
            if not detection.is_property:
                continue
            if validate_candidate(candidate):
                continue
            candidate.confidence = round(min(1.0, max(candidate.confidence, detection.confidence)), 2)
            filtered.append(candidate)
        candidates = filtered

        unique, _duplicates = find_duplicates(candidates)
        ranked = sorted(
            unique,
            key=lambda c: score_candidate(c, intent, c.query or query_list[0])["score"],
            reverse=True,
        )
        ranked = ranked[: max(settings.WEB_SEARCH_MAX_RESULTS, 1)]

        docs = [to_doc(candidate, candidate.query or query_list[0], cache_key) for candidate in ranked]
        inserted = self.repository.persist(docs)

        if enrich and ranked:
            ids = [str(oid) for oid in self._stored_ids(docs)]
            DiscoveryGeocoder(self.db, limit=settings.WEB_DISCOVERY_OSM_ENRICH_LIMIT).enrich(ids)

        cards: list[dict[str, Any]] = []
        for doc in docs:
            stored = self.repository.by_canonical_url(doc["canonical_url"])
            if not stored:
                continue
            score = score_candidate(_candidate_from_doc(stored), intent, stored.get("query") or query_list[0])["score"]
            cards.append(doc_to_card(
                stored,
                saved=bool(saved_ids and str(stored["_id"]) in saved_ids),
                rank_score=score,
            ))
        cards.sort(key=lambda item: (item.get("rank_score") or 0), reverse=True)

        cache_payload = [
            {"query": query, "result": result.model_dump()}
            for query, result in provider_response["items"]
        ]
        self.cache.set(cache_key, query_list[0], intent.model_dump(), cache_payload, provider.name)

        return WebDiscoveryOutcome(
            status="available", code="OK", message=None, cards=cards,
            queries_used=query_list, provider=provider.name,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            inserted=inserted,
            sources_searched=[s.name for s in routed_sources],
        )

    def _stored_ids(self, docs: list[dict[str, Any]]) -> list:
        """Return _id values for persisted canonical URLs."""
        ids: list = []
        for doc in docs:
            stored = self.repository.by_canonical_url(doc.get("canonical_url") or "")
            if stored:
                ids.append(stored["_id"])
        return ids

    def _run_queries(self, provider, query_list, max_results) -> dict[str, Any]:
        """Run bounded provider searches sequentially (concurrency-safe, cost-bound)."""
        items: list[tuple[str, WebSearchResult]] = []
        total_results = 0
        count = max_results or settings.WEB_SEARCH_MAX_RESULTS
        for query in query_list:
            if not query or not query.strip():
                continue
            self._limiter.acquire(user_key="discovery_request")
            try:
                self._health.record_start()
                started = time.perf_counter()
                response = provider.search(query, count=count)
                latency_ms = round((time.perf_counter() - started) * 1000, 1)
                self._health.record_success(latency_ms)
            except WebSearchRateLimitError as exc:
                self._health.record_rate_limited()
                raise
            except WebSearchError as exc:
                self._health.record_error(exc.code)
                raise
            finally:
                self._limiter.release()
            for result in response.results or []:
                items.append((query, result))
            total_results += response.total_results or 0
        return {"items": items, "total_results": total_results}

    def _cards_from_cached(self, payload: list[dict[str, Any]], intent: SearchIntent, saved_ids, stale: bool = False) -> list[dict[str, Any]]:
        """Rebuild cards from a cached payload of {query, result} entries."""
        cards: list[dict[str, Any]] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            raw = entry.get("result")
            if isinstance(raw, dict):
                result = WebSearchResult(**raw)
            else:
                result = WebSearchResult(**entry)
            candidate = self.extractor.extract(result, intent_city=intent.city)
            if candidate is None:
                continue
            candidate.query = entry.get("query") if isinstance(entry.get("query"), str) else ""
            cached_doc = self.repository.by_canonical_url(candidate.url)
            if cached_doc:
                score = score_candidate(candidate, intent, candidate.query or "")["score"]
                cards.append(doc_to_card(
                    cached_doc,
                    saved=bool(saved_ids and str(cached_doc["_id"]) in saved_ids),
                    rank_score=score,
                ))
            else:
                card = candidate.model_dump()
                card["id"] = candidate.url
                card["freshness_label"] = freshness_label(candidate.discovered_at, candidate.page_fetched)
                card["verification_status"] = "web_discovery"
                cards.append(card)
        # Deduplicate cached cards by canonical URL (multiple provider queries can overlap).
        from app.discovery.deduplication import canonical_url as _canon
        unique_cards = []
        seen_urls = set()
        for card in cards:
            key = _canon(card.get('url') or '')
            if key and key in seen_urls:
                continue
            if key:
                seen_urls.add(key)
            unique_cards.append(card)
        return unique_cards


def _candidate_from_doc(doc: dict[str, Any]):
    """Rehydrate a lightweight candidate for scoring from a persisted doc."""
    from app.discovery.models import PropertyCandidate

    return PropertyCandidate(
        title=doc.get("title") or "",
        url=doc.get("result_url") or "",
        source_domain=doc.get("source_domain") or "",
        source_name=doc.get("source_name"),
        description=doc.get("description"),
        price=doc.get("price"),
        transaction_type=doc.get("transaction_type"),
        bedrooms=doc.get("bedrooms"),
        area=doc.get("area"),
        area_unit=doc.get("area_unit"),
        location_text=doc.get("location_text"),
        city=doc.get("city"),
        locality=doc.get("locality"),
        discovered_at=doc.get("discovered_at"),
    )
