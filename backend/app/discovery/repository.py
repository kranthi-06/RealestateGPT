"""web_property_discoveries + saved_discoveries repositories.

Web discoveries are short-lived, search-provider-backed records — separate from
canonical ``properties``. They are never automatically promoted into verified
inventory; promotion is an explicit, authorized backend process.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.config import settings
from app.discovery.deduplication import canonical_url


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_doc(candidate: Any, query: str, query_hash: str) -> dict[str, Any]:
    """Serialize a PropertyCandidate into the web_property_discoveries doc."""
    now = _utcnow()
    return {
        "query": query,
        "query_hash": query_hash,
        "result_url": candidate.url,
        "canonical_url": canonical_url(candidate.url),
        "source_domain": candidate.source_domain,
        "source_name": candidate.source_name,
        "title": candidate.title,
        "description": candidate.description,
        "price": candidate.price,
        "currency": candidate.currency,
        "transaction_type": candidate.transaction_type,
        "property_type": candidate.property_type,
        "bedrooms": candidate.bedrooms,
        "bathrooms": candidate.bathrooms,
        "area": candidate.area,
        "area_unit": candidate.area_unit,
        "area_sqft": candidate.area_sqft,
        "location_text": candidate.location_text,
        "city": candidate.city,
        "locality": candidate.locality,
        "furnishing": candidate.furnishing,
        "image_url": candidate.image_url,
        "source_listing_id": candidate.source_listing_id,
        "extraction_method": candidate.extraction_method,
        "confidence": candidate.confidence,
        "provider": candidate.provider,
        "page_age": candidate.page_age,
        "page_fetched_at": candidate.page_fetched,
        "discovered_at": candidate.discovered_at or now,
        "latitude": getattr(candidate, "latitude", None),
        "longitude": getattr(candidate, "longitude", None),
        "location_source": getattr(candidate, "location_source", None),
        "expires_at": now + timedelta(hours=settings.WEB_DISCOVERY_TTL_HOURS),
        "created_at": now,
        "updated_at": now,
    }


class WebDiscoveryRepository:
    COLLECTION = "web_property_discoveries"

    def __init__(self, db) -> None:
        self.db = db
        self.coll = db[self.COLLECTION]

    def persist(self, docs: list[dict[str, Any]]) -> int:
        """Insert discovery documents; skip duplicates by canonical_url within the
        batch and against already-stored rows. Idempotent by design.
        """
        inserted = 0
        existing = set()
        for doc in docs:
            url = doc.get("canonical_url") or ""
            if url in existing:
                continue
            if url and self.coll.find_one({"canonical_url": url}, {"_id": 1}):
                existing.add(url)
                continue
            self.coll.insert_one(doc)
            if url:
                existing.add(url)
            inserted += 1
        return inserted

    def by_id(self, discovery_id: str) -> Optional[dict[str, Any]]:
        try:
            from bson import ObjectId

            oid = ObjectId(discovery_id)
        except Exception:
            return None
        return self.coll.find_one({"_id": oid})

    def by_canonical_url(self, url: str) -> Optional[dict[str, Any]]:
        if not url:
            return None
        return self.coll.find_one({"canonical_url": canonical_url(url)})
    
    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return list(self.coll.find({}).sort("discovered_at", -1).limit(limit))

    def update_coordinates(self, discovery_id, latitude: float, longitude: float, source: str) -> bool:
        result = self.coll.update_one(
            {"_id": discovery_id},
            {
                "$set": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "location": {"type": "Point", "coordinates": [longitude, latitude]},
                    "location_source": source,
                    "updated_at": _utcnow(),
                }
            },
        )
        return result.modified_count == 1

    def cleanup(self) -> int:
        result = self.coll.delete_many({"expires_at": {"$lt": _utcnow()}})
        return int(result.deleted_count)


class SavedDiscoveryRepository:
    """User-scoped 'Save discovery for later'.

    Deliberately distinct from ``saved_properties`` — a saved discovery is
    clearly a *discovery*, not a verified RealEstateGPT property.
    """

    COLLECTION = "saved_discoveries"

    def __init__(self, db) -> None:
        self.db = db
        self.coll = db[self.COLLECTION]

    def save(self, user_id: int, discovery_id: str, notes: Optional[str] = None) -> bool:
        existing = self.coll.find_one({"user_id": user_id, "discovery_id": discovery_id})
        if existing:
            return True
        self.coll.insert_one({
            "user_id": user_id,
            "discovery_id": discovery_id,
            "notes": notes,
            "created_at": _utcnow(),
        })
        return True

    def unsave(self, user_id: int, discovery_id: str) -> bool:
        result = self.coll.delete_one({"user_id": user_id, "discovery_id": discovery_id})
        return result.deleted_count > 0

    def is_saved(self, user_id: int, discovery_id: str) -> bool:
        return self.coll.find_one({"user_id": user_id, "discovery_id": discovery_id}) is not None

    def list_for_user(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        return list(self.coll.find({"user_id": user_id}).sort("created_at", -1).limit(limit))

