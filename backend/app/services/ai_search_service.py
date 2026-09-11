"""Database-first property discovery with deterministic, explainable ranking."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from app.ai.query_parser import parse_query
from app.ai.scoring import ScoreContext, score_property
from app.location.service import LocationService
from app.providers.location import LocationProviderUnavailable
from app.repositories.property_repo import PropertyRepository
from app.schemas.ai import ParsedQuery, ScoredProperty, SearchIntent

MAX_CANDIDATES = 30
MAX_LOCATION_ENRICHMENTS = 12
MAX_ROUTE_ENRICHMENTS = 10


def _payload(prop) -> dict[str, Any]:
    return {
        "id": prop.id, "title": prop.title, "city": prop.city, "locality": prop.locality,
        "property_type": prop.property_type, "price": prop.price, "area_sqft": prop.area_sqft,
        "bedrooms": prop.bedrooms, "bathrooms": prop.bathrooms,
        "furnishing": prop.furnishing, "description": prop.description,
        "amenities": [item.name for item in prop.amenities], "data_quality_score": prop.data_quality_score,
    }


class AiSearchService:
    """SearchIntent -> MongoDB candidate set -> bounded OSM enrichment -> ranking."""
    def __init__(self, db) -> None:
        self.db = db
        self.repo = PropertyRepository(db)

    def search(self, query_text: str, limit: int = 12, user_filters: Optional[dict] = None, parsed: Optional[ParsedQuery] = None) -> dict:
        started = time.perf_counter()
        intent = SearchIntent.model_validate((parsed or parse_query(query_text)).model_dump())
        filters = self._filters(intent, user_filters or {})
        filters.update(page=1, page_size=min(MAX_CANDIDATES, max(limit * 2, limit)))
        db_started = time.perf_counter()
        candidates, total = self.repo.search_properties(**filters)
        database_latency_ms = round((time.perf_counter() - db_started) * 1000, 1)
        nearby, commute, warnings, location_latency_ms = self._location_context(candidates, intent)
        results = self._score(candidates, intent, nearby, commute, limit)
        return {
            "query": query_text, "parsed": intent, "hard_filtered_count": total, "total": total,
            "results": results, "exceeded": total < limit,
            "warning": "; ".join(warnings) if warnings else None,
            "metrics": {"database_latency_ms": database_latency_ms, "location_latency_ms": location_latency_ms,
                        "total_latency_ms": round((time.perf_counter() - started) * 1000, 1),
                        "candidate_count": len(candidates)},
        }

    @staticmethod
    def _filters(intent: SearchIntent, supplied: dict) -> dict:
        allowed = {"city", "locality", "property_type", "listing_type", "bedrooms", "bathrooms", "min_price", "max_price", "min_area", "max_area", "furnishing", "amenities", "latitude", "longitude", "radius_km", "sort_by", "sort_order"}
        filters = {key: value for key, value in supplied.items() if key in allowed and not str(key).startswith("$")}
        for key in ("city", "locality", "property_type", "listing_type", "bedrooms", "bathrooms", "min_price", "max_price", "min_area", "max_area", "furnishing", "amenities"):
            value = getattr(intent, key, None)
            if value is not None and key not in filters:
                filters[key] = value
        return filters

    def _location_context(self, candidates: list, intent: SearchIntent) -> tuple[dict[int, dict[str, float]], dict[int, float], list[str], float]:
        if not candidates or (not intent.nearby_requirements and not intent.commute_destination):
            return {}, {}, [], 0.0
        started, warnings = time.perf_counter(), []
        location = LocationService(self.db)
        nearby: dict[int, dict[str, float]] = {}
        commute: dict[int, float] = {}
        targets = [p for p in candidates if p.latitude is not None and p.longitude is not None][:MAX_LOCATION_ENRICHMENTS]
        categories = sorted({item.type for item in intent.nearby_requirements})
        try:
            if categories:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    pending = {executor.submit(self._nearest, location, prop, category): (prop.id, category) for prop in targets for category in categories}
                    for future in as_completed(pending):
                        prop_id, category = pending[future]
                        try:
                            distance = future.result()
                            if distance is not None:
                                nearby.setdefault(prop_id, {})[category] = distance
                        except LocationProviderUnavailable:
                            warnings.append("Live nearby-place enrichment is temporarily unavailable.")
                            break
            if intent.commute_destination:
                destination = location.provider.geocode(intent.commute_destination)
                with ThreadPoolExecutor(max_workers=4) as executor:
                    pending = {executor.submit(location.provider.route, (prop.latitude, prop.longitude), (destination["latitude"], destination["longitude"]), "DRIVE"): prop.id for prop in targets[:MAX_ROUTE_ENRICHMENTS]}
                    for future in as_completed(pending):
                        try:
                            result = future.result()
                            commute[pending[future]] = float(result["duration_minutes"])
                        except LocationProviderUnavailable:
                            warnings.append("Live route enrichment is temporarily unavailable.")
                            break
        except LocationProviderUnavailable:
            warnings.append("Live location enrichment is temporarily unavailable.")
        return nearby, commute, list(dict.fromkeys(warnings)), round((time.perf_counter() - started) * 1000, 1)

    @staticmethod
    def _nearest(location: LocationService, prop, category: str) -> Optional[float]:
        places = location.provider.nearby(prop.latitude, prop.longitude, category, 5.0)
        return float(places[0]["distance_km"]) if places and places[0].get("distance_km") is not None else None

    @staticmethod
    def _score(candidates: list, intent: SearchIntent, nearby: dict[int, dict[str, float]], commute: dict[int, float], limit: int) -> list[ScoredProperty]:
        results = []
        for prop in candidates:
            scored = score_property(_payload(prop), intent.model_dump(), ScoreContext(nearby=nearby.get(prop.id, {})), None)
            reasons = list(scored["positive_factors"])
            if prop.data_quality_score >= 80:
                reasons.append("High property data quality")
            if prop.id in commute:
                duration = commute[prop.id]
                if intent.commute_max_minutes and duration <= intent.commute_max_minutes:
                    reasons.append(f"OSRM driving route estimate: {duration:.0f} minutes, within your limit")
                else:
                    reasons.append(f"OSRM driving route estimate: {duration:.0f} minutes")
            # Quality is a deterministic, explicitly visible ranking dimension.
            score = min(100.0, round(scored["overall_score"] * 0.9 + prop.data_quality_score * 0.1, 1))
            results.append(ScoredProperty(
                property_id=prop.id, title=prop.title, slug=prop.slug, price=prop.price,
                locality=prop.locality, city=prop.city, property_type=prop.property_type,
                bedrooms=prop.bedrooms, bathrooms=prop.bathrooms, area_sqft=prop.area_sqft,
                price_per_sqft=prop.price_per_sqft, is_featured=prop.is_featured,
                is_synthetic=prop.is_synthetic, verification_status=prop.verification_status,
                image_urls=prop.image_urls, overall_score=score,
                component_scores=scored["component_scores"], explanation=scored["explanation"],
                positive_factors=reasons[:5], negative_factors=scored["negative_factors"],
                semantic_similarity=None, est_price=None,
            ))
        return sorted(results, key=lambda item: item.overall_score, reverse=True)[:limit]
