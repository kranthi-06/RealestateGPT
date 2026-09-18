"""Property ingestion pipeline for approved property providers.

The service accepts raw records from a caller-supplied licensed provider. It
does not fetch arbitrary URLs or scrape property websites.

Pipeline: normalize -> validate -> deduplicate (confidence-scored) -> publish.
Publishing keeps provenance/freshness fields and never lets one provider's
record overwrite a conflicting provider's record.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import ValidationError

from app.models.property import Property
from app.repositories.property_repo import PropertyRepository

_SOURCE_TYPE_WHITELIST = {"licensed_feed", "partner_api", "admin", "user", "demo"}


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return value[:180] or "property"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_area_sqft(area, area_unit, area_sqft) -> Optional[float]:
    if area_sqft:
        return float(area_sqft)
    if area and area_unit == "sqft":
        return float(area)
    if area and area_unit == "sqm":
        return round(float(area) * 10.7639, 2)
    return None


class PropertyValidationService:
    def validate(self, payload: dict[str, Any]) -> Property:
        """Validate canonical data; invalid records are rejected, never published."""
        return Property.model_validate(payload)


class PropertyNormalizationService:
    """Translate an approved provider record to the canonical model shape."""

    def normalize(self, raw: dict[str, Any], source: str, source_type: str) -> dict[str, Any]:
        payload = dict(raw)
        payload["source"] = source
        payload["source_type"] = source_type

        listing_id = payload.get("source_listing_id") or payload.get("source_id")
        if listing_id:
            payload["source_listing_id"] = str(listing_id)
            payload["source_id"] = str(listing_id)

        if not payload.get("slug"):
            stable = payload.get("source_listing_id") or payload.get("title", "property")
            payload["slug"] = _slug(f"{source}-{stable}")

        # transaction_type / listing_type normalize toward the canonical pair.
        transaction_type = payload.get("transaction_type") or payload.get("listing_type")
        if transaction_type in ("rent", "rental", "lease"):
            payload["listing_type"] = "rent"
            payload["transaction_type"] = "rent"
        elif transaction_type in ("sale", "buy", "resale"):
            payload["listing_type"] = "sale"
            payload["transaction_type"] = "sale"

        if payload.get("rent_amount") and payload.get("listing_type") == "rent" and not payload.get("price"):
            payload["price"] = payload["rent_amount"]

        # Area normalization
        payload["area_sqft"] = _coerce_area_sqft(
            payload.get("area"), payload.get("area_unit"), payload.get("area_sqft")
        )
        if payload.get("area_sqft") and not payload.get("price_per_sqft"):
            price = payload.get("price")
            if price and float(price) > 0:
                payload["price_per_sqft"] = round(float(price) / float(payload["area_sqft"]), 2)

        # Images: string urls / dicts / comma-separated strings all normalize.
        if payload.get("images") is None and payload.get("image_urls"):
            payload["images"] = [
                url.strip() for url in str(payload["image_urls"]).split(",") if url.strip()
            ]
        images = payload.get("images") or []
        normalized_images = []
        for index, image in enumerate(images):
            if isinstance(image, str):
                normalized_images.append({"url": image.strip(), "display_order": index})
            elif isinstance(image, dict) and image.get("url"):
                item = dict(image)
                item.setdefault("display_order", index)
                normalized_images.append(item)
        if normalized_images:
            payload["images"] = normalized_images

        # Amenities: plain string lists become Amenity dicts.
        amenities = payload.get("amenities") or []
        normalized_amenities = []
        for index, amenity in enumerate(amenities):
            if isinstance(amenity, str):
                normalized_amenities.append({"id": index, "name": amenity})
            elif isinstance(amenity, dict) and amenity.get("name"):
                item = dict(amenity)
                item.setdefault("id", index)
                normalized_amenities.append(item)
        if normalized_amenities:
            payload["amenities"] = normalized_amenities

        # Status defaults: a fresh provider record is active until proven otherwise.
        if not payload.get("status"):
            payload["status"] = "active"
        if not payload.get("is_active"):
            payload["is_active"] = payload.get("status") not in (
                "inactive", "sold", "rented", "expired", "removed"
            )

        # Provenance: real provider records are never synthetic.
        if source_type != "demo" and payload.get("source_type") != "demo":
            payload["is_synthetic"] = False
            if payload.get("source_type") in {"licensed_feed", "partner_api", "admin"}:
                payload["verification_status"] = payload.get("verification_status") or "verified"
        return payload


@dataclass
class DuplicateMatch:
    property_id: Optional[int] = None
    confidence: float = 0.0
    method: str = "none"  # primary | secondary


class DeduplicationEngine:
    """Confidence-scored duplicate detection.

    Thresholds:
      90+   -> likely duplicate (updates flow into the canonical listing)
      60-89 -> possible duplicate (recorded for review; kept separate)
      <60   -> separate listing
    """

    MERGE_THRESHOLD = 90.0
    REVIEW_THRESHOLD = 60.0

    @staticmethod
    def normalize_address(address: Optional[str]) -> str:
        """Sortable, lowercase token key of an address."""
        if not address:
            return ""
        value = re.sub(
            r"(no\.?|flat|apartment|apt|plot|survey)\s*[0-9/-]+",
            "",
            str(address).lower(),
        )
        tokens = [
            t for t in re.split(r"[^a-z0-9]+", value)
            if t and t not in {"the", "and", "road", "rd", "street", "st", "near"}
        ]
        return " ".join(sorted(set(tokens)))

    @staticmethod
    def haversine_km(lat1, lon1, lat2, lon2) -> Optional[float]:
        try:
            from math import asin, cos, radians, sin, sqrt

            lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
            lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
            a = (
                sin((lat2 - lat1) / 2) ** 2
                + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
            )
            return 6371.0 * 2 * asin(sqrt(a))
        except (TypeError, ValueError):
            return None

    def confidence(self, candidate: Property, existing: Property) -> DuplicateMatch:
        """Compute a 0-100 duplicate confidence score between two properties."""
        if (
            candidate.source
            and existing.source
            and candidate.source_listing_id
            and existing.source_listing_id
        ):
            if (
                candidate.source == existing.source
                and candidate.source_listing_id == existing.source_listing_id
            ):
                return DuplicateMatch(property_id=existing.id, confidence=100.0, method="primary")

        score = 0.0
        if (candidate.city or "").lower() == (existing.city or "").lower():
            score += 10
        if candidate.property_type and existing.property_type:
            if candidate.property_type.lower() == existing.property_type.lower():
                score += 10
        if candidate.bedrooms is not None and existing.bedrooms is not None:
            if candidate.bedrooms == existing.bedrooms:
                score += 15
        if candidate.area_sqft and existing.area_sqft:
            diff = abs(candidate.area_sqft - existing.area_sqft) / max(
                candidate.area_sqft, existing.area_sqft
            )
            if diff <= 0.10:
                score += 15
            elif diff <= 0.25:
                score += 8
        if candidate.price and existing.price:
            diff = abs(candidate.price - existing.price) / max(candidate.price, existing.price)
            if diff <= 0.15:
                score += 15
            elif diff <= 0.30:
                score += 8
        dist = self.haversine_km(
            candidate.latitude, candidate.longitude,
            existing.latitude, existing.longitude,
        )
        if dist is not None:
            if dist <= 0.15:
                score += 25
            elif dist <= 0.5:
                score += 15
            elif dist <= 1.5:
                score += 5
        cand_addr = self.normalize_address(candidate.address)
        existing_addr = self.normalize_address(existing.address)
        if cand_addr and existing_addr:
            cand_tokens = set(cand_addr.split())
            existing_tokens = set(existing_addr.split())
            if cand_tokens and existing_tokens:
                jaccard = len(cand_tokens & existing_tokens) / len(cand_tokens | existing_tokens)
                if jaccard >= 0.6:
                    score += 20
                elif jaccard >= 0.3:
                    score += 10

        return DuplicateMatch(
            property_id=existing.id,
            confidence=round(min(score, 99.9), 1),
            method="secondary",
        )

    def find(
        self, repository: PropertyRepository, candidate: Property, primary: Optional[Property]
    ) -> DuplicateMatch:
        """Locate the closest existing record for a candidate.

        Primary (source+source_listing_id) is definitive; secondary matching is
        bounded to same-city candidates so it stays cheap and safe.
        """
        if primary is not None:
            return DuplicateMatch(property_id=primary.id, confidence=100.0, method="primary")

        locality = getattr(candidate, "locality", None)
        query = {"is_active": True, "city": candidate.city}
        if locality:
            query["locality"] = locality
        docs = list(repository.coll.find(query).limit(50))
        best = DuplicateMatch(confidence=0.0, method="none")
        for doc in docs:
            existing = Property.from_doc(doc)
            if existing is None or existing.id == candidate.id:
                continue
            match = self.confidence(candidate, existing)
            if match.confidence > best.confidence:
                best = match
        return best


class PropertyDeduplicationService:
    def __init__(self, repository: PropertyRepository) -> None:
        self.repository = repository
        self.engine = DeduplicationEngine()

    def existing(self, property_: Property) -> Optional[Property]:
        listing_id = property_.source_listing_id or property_.source_id
        doc = None
        if property_.source and listing_id:
            doc = (
                self.repository.coll.find_one(
                    {"source": property_.source, "source_listing_id": listing_id}
                )
                or self.repository.coll.find_one(
                    {"source": property_.source, "source_id": listing_id}
                )
            )
        if doc is None:
            doc = self.repository.coll.find_one({"slug": property_.slug, "is_active": True})
        return Property.from_doc(doc)


@dataclass
class IngestionResult:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    rejected: int = 0
    failed: int = 0
    duplicates: int = 0
    reviews: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    review_candidates: list[dict[str, Any]] = field(default_factory=list)


class PropertyIngestionService:
    """SOURCE -> validate -> normalize -> deduplicate -> publish (idempotent)."""

    def __init__(self, repository: PropertyRepository) -> None:
        self.repository = repository
        self.normalizer = PropertyNormalizationService()
        self.validator = PropertyValidationService()
        self.deduplicator = PropertyDeduplicationService(repository)

    @staticmethod
    def quality_score(property_: Property) -> float:
        fields = [
            property_.title, property_.price, property_.property_type, property_.city,
            property_.source, property_.source_type, property_.source_listing_id,
            property_.latitude, property_.longitude, property_.area, property_.bedrooms,
        ]
        return round(
            sum(value is not None and value != "" for value in fields) / len(fields) * 100,
            1,
        )

    def ingest(
        self,
        raw_records: list[dict[str, Any]],
        *,
        source: str,
        source_type: str,
    ) -> IngestionResult:
        if source_type not in _SOURCE_TYPE_WHITELIST:
            raise ValueError("Unsupported property source type")
        result = IngestionResult(fetched=len(raw_records))
        now = _now()

        for raw in raw_records:
            try:
                candidate = self.validator.validate(
                    self.normalizer.normalize(raw, source, source_type)
                )
            except ValidationError as exc:
                result.rejected += 1
                first = exc.errors()[0] if exc.errors() else {}
                reason = f"{first.get('loc', 'payload')}: {first.get('msg', 'invalid')}"
                result.rejection_reasons[reason] = result.rejection_reasons.get(reason, 0) + 1
                continue
            except (TypeError, ValueError, KeyError):
                result.rejected += 1
                result.rejection_reasons["malformed_record"] = (
                    result.rejection_reasons.get("malformed_record", 0) + 1
                )
                continue

            candidate.data_quality_score = self.quality_score(candidate)
            try:
                self._resolve_and_store(candidate, now, result)
            except Exception:
                result.failed += 1
        return result

    def _resolve_and_store(self, candidate: Property, now: datetime, result: IngestionResult) -> None:
        primary = self.deduplicator.existing(candidate)
        if primary is not None:
            # Definitive same-listing sighting: refresh, never duplicate.
            self._apply_refresh(primary, candidate, now)
            result.updated += 1
            return

        match = self.deduplicator.engine.find(self.repository, candidate, primary)
        if match.confidence >= DeduplicationEngine.MERGE_THRESHOLD:
            existing = Property.from_doc(
                self.repository.coll.find_one({"_id": match.property_id})
            )
            if existing is not None:
                self._apply_refresh(existing, candidate, now)
                result.duplicates += 1
                return
        elif match.confidence >= DeduplicationEngine.REVIEW_THRESHOLD:
            result.reviews += 1
            result.review_candidates.append({
                "candidate_slug": candidate.slug,
                "possible_duplicate_of": match.property_id,
                "confidence": match.confidence,
            })
            self.repository.db["dedup_reviews"].insert_one({
                "candidate_slug": candidate.slug,
                "possible_duplicate_of": match.property_id,
                "confidence": match.confidence,
                "status": "open",
                "created_at": now,
            })

        self._set_freshness(candidate, now, is_new=True)
        self.repository.create_property(candidate)
        self._enqueue_geocoding(candidate)
        result.created += 1

    def _set_freshness(self, property_: Property, now: datetime, *, is_new: bool) -> None:
        if is_new:
            property_.first_seen_at = property_.first_seen_at or now
            property_.listed_at = property_.listed_at or now
        property_.last_seen_at = now
        property_.last_verified_at = now
        property_.stale_at = None
        property_.expired_at = None
        property_.status = "active"
        if property_.listing_type == "rent" and property_.rent_amount is None:
            property_.rent_amount = property_.price

    def _apply_refresh(self, existing: Property, candidate: Property, now: datetime) -> None:
        """Merge a fresh sighting into an existing record idempotently."""
        self._set_freshness(existing, now, is_new=False)
        updates: dict[str, Any] = {
            "last_seen_at": now,
            "last_verified_at": now,
            "status": "active",
            "stale_at": None,
            "expired_at": None,
            "updated_at": now,
        }
        # Prefer the freshest values but never clobber identifiers from another source.
        for field_name in (
            "title", "description", "price", "price_per_sqft", "property_type",
            "transaction_type", "listing_type", "bedrooms", "bathrooms", "balconies",
            "area", "area_unit", "area_sqft", "carpet_area_sqft", "floor", "total_floors",
            "property_age", "facing", "furnishing", "parking", "construction_status",
            "address", "locality", "city", "state", "pincode", "postal_code",
            "latitude", "longitude", "builder_name", "project_name",
            "maintenance", "maintenance_charge", "security_deposit", "brokerage",
            "rent_amount", "rent_period", "amenities", "images", "image_urls", "source_url",
        ):
            value = getattr(candidate, field_name, None)
            if value not in (None, "", [], {}):
                updates[field_name] = value

        # Never let a provider overwrite a demo/seed record's source identity.
        if existing.is_synthetic and candidate.source_type != "demo":
            updates.pop("source", None)
            updates.pop("source_type", None)
            updates.pop("is_synthetic", None)

        self.repository.update_property(existing.id, updates)
        self._enqueue_geocoding(existing)

    def _enqueue_geocoding(self, property_: Property) -> None:
        """Queue properties missing coordinates for the geocoding worker."""
        if property_.latitude is not None and property_.longitude is not None:
            return
        address = (property_.address or "").strip() or (
            f"{property_.locality or ''}, {property_.city or ''}".strip(", ")
            if (property_.locality or property_.city)
            else ""
        )
        if not address:
            return
        self.repository.db["geocode_queue"].update_one(
            {"property_id": property_.id, "status": {"$in": ["pending", "failed"]}},
            {"$set": {"address": address, "updated_at": _now()}},
            upsert=True,
        )