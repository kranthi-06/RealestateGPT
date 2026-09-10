"""Hybrid property search using validated database facts."""
from __future__ import annotations

from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.ai.embeddings import get_embedding_service
from app.ai.query_parser import parse_query
from app.ai.scoring import ScoreContext, score_property
from app.location.service import haversine_km
from app.ml.price_estimator import build_catalog, get_price_estimator
from app.models.platform import NearbyPlace
from app.models.property import Property
from app.repositories.property_repo import PropertyRepository
from app.schemas.ai import ParsedQuery, ScoredProperty


def _text(prop: Property) -> str:
    return " ".join(filter(None, [prop.title, prop.locality, prop.city, prop.builder_name, (prop.description or "")[:400]]))


def _payload(prop: Property) -> dict:
    return {"id": prop.id, "title": prop.title, "city": prop.city, "locality": prop.locality,
            "property_type": prop.property_type, "price": prop.price, "area_sqft": prop.area_sqft,
            "bedrooms": prop.bedrooms, "bathrooms": prop.bathrooms, "price_per_sqft": prop.price_per_sqft,
            "furnishing": prop.furnishing, "property_age": prop.property_age, "description": prop.description,
            "amenities": [item.name for item in (prop.amenities or [])]}


class AiSearchService:
    def __init__(self, db: Session) -> None:
        self.db, self.repo = db, PropertyRepository(db)

    def search(self, query_text: str, limit: int = 12, user_filters: Optional[Dict] = None,
               parsed: Optional[ParsedQuery] = None) -> dict:
        pq = parsed or parse_query(query_text)
        filters = dict(user_filters or {})
        for field in ("city", "locality", "property_type", "bedrooms", "min_price", "max_price", "min_area", "max_area", "furnishing"):
            value = getattr(pq, field)
            if value is not None and value != "" and not filters.get(field):
                filters[field] = value
        filters.setdefault("listing_type", pq.listing_type)
        filters.update(page=1, page_size=min(50, max(30, limit * 3)))
        candidates, hard_total = self.repo.search(**filters)
        warning = None
        if len(candidates) < limit:
            known = {prop.id for prop in candidates}
            candidates.extend(prop for prop in self._semantic_fallback(pq, limit * 3) if prop.id not in known)
            if len(candidates) > hard_total:
                warning = "Some results are close semantic matches because few listings met every hard filter."
        results = self._score(candidates, pq, limit)
        return {"query": query_text, "parsed": pq, "hard_filtered_count": hard_total, "total": len(results),
                "results": results, "exceeded": len(results) < min(limit, 6), "warning": warning}

    def _semantic_fallback(self, pq: ParsedQuery, limit: int) -> List[Property]:
        catalog = self.db.query(Property).filter(Property.is_active == True, Property.listing_type == pq.listing_type).all()  # noqa: E712
        if not catalog:
            return []
        query, embedder = " ".join(pq.keywords) or pq.raw_text, get_embedding_service()
        texts = [_text(prop) for prop in catalog]
        embedder.fit_documents(texts + [query])
        sims = embedder.similarity_batch(query, texts)
        return [prop for prop, _ in sorted(zip(catalog, sims), key=lambda row: row[1], reverse=True)[:limit]]

    def _nearby(self, candidates: List[Property]) -> Dict[int, Dict[str, float]]:
        cities = list({prop.city for prop in candidates if prop.city})
        places = self.db.query(NearbyPlace).filter(NearbyPlace.city.in_(cities)).all() if cities else []
        result: Dict[int, Dict[str, float]] = {}
        for prop in candidates:
            nearest: Dict[str, float] = {}
            if prop.latitude is not None and prop.longitude is not None:
                for place in places:
                    if place.city.lower() == prop.city.lower():
                        distance = haversine_km(prop.latitude, prop.longitude, place.latitude, place.longitude)
                        if distance < nearest.get(place.place_type, float("inf")):
                            nearest[place.place_type] = distance
            result[prop.id] = nearest
        return result

    def _score(self, candidates: List[Property], pq: ParsedQuery, limit: int) -> List[ScoredProperty]:
        if not candidates:
            return []
        catalog, estimates = build_catalog(candidates), {}
        if len(catalog) >= 4:
            estimator = get_price_estimator()
            for prop in candidates:
                row = next((item for item in catalog if item["id"] == prop.id), None)
                if row:
                    estimates[prop.id] = estimator.estimate(row, catalog)
        query, embedder = " ".join(pq.keywords) or pq.raw_text, get_embedding_service()
        texts = [_text(prop) for prop in candidates]
        embedder.fit_documents(texts + [query])
        nearby, sims, results = self._nearby(candidates), embedder.similarity_batch(query, texts), []
        for prop, similarity in zip(candidates, sims):
            estimate = estimates.get(prop.id, {})
            scored = score_property(_payload(prop), pq.model_dump(exclude={"raw_text"}),
                ScoreContext(est_price=estimate.get("estimated_price"), est_low=estimate.get("lower_bound"),
                             est_high=estimate.get("upper_bound"), nearby=nearby.get(prop.id, {})), None)
            results.append(ScoredProperty(property_id=prop.id, title=prop.title, slug=prop.slug, price=prop.price,
                locality=prop.locality, city=prop.city, property_type=prop.property_type, bedrooms=prop.bedrooms,
                bathrooms=prop.bathrooms, area_sqft=prop.area_sqft, price_per_sqft=prop.price_per_sqft,
                is_featured=prop.is_featured, is_synthetic=prop.is_synthetic, verification_status=prop.verification_status,
                image_urls=prop.image_urls, overall_score=round(scored["overall_score"] * .8 + similarity * 20, 1),
                component_scores=scored["component_scores"], explanation=scored["explanation"],
                positive_factors=scored["positive_factors"], negative_factors=scored["negative_factors"],
                semantic_similarity=round(similarity, 4), est_price=estimate.get("estimated_price")))
        return sorted(results, key=lambda item: item.overall_score, reverse=True)[:limit]
