"""Property ingestion pipeline for approved property providers.

The service accepts raw records from a caller-supplied licensed provider. It
does not fetch arbitrary URLs or scrape property websites.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.models.property import Property
from app.repositories.property_repo import PropertyRepository


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return value[:180] or "property"


class PropertyValidationService:
    def validate(self, payload: dict[str, Any]) -> Property:
        """Validate canonical data; invalid records are rejected, never published."""
        return Property.model_validate(payload)


class PropertyNormalizationService:
    def normalize(self, raw: dict[str, Any], source: str, source_type: str) -> dict[str, Any]:
        """Translate an approved provider record to the canonical model shape."""
        payload = dict(raw)
        payload["source"] = source
        payload["source_type"] = source_type
        if not payload.get("slug"):
            stable = payload.get("source_id") or payload.get("title", "property")
            payload["slug"] = _slug(f"{source}-{stable}")
        if payload.get("images") is None and payload.get("image_urls"):
            payload["images"] = [url.strip() for url in str(payload["image_urls"]).split(",") if url.strip()]
        return payload


class PropertyDeduplicationService:
    def __init__(self, repository: PropertyRepository) -> None:
        self.repository = repository

    def existing(self, property_: Property) -> Property | None:
        if property_.source_id:
            doc = self.repository.coll.find_one({"source": property_.source, "source_id": property_.source_id})
            return Property.from_doc(doc)
        return self.repository.get_by_slug(property_.slug)


@dataclass
class IngestionResult:
    created: int = 0
    updated: int = 0
    rejected: int = 0


class PropertyIngestionService:
    """SOURCE → validate → normalize → deduplicate → quality score → publish."""
    def __init__(self, repository: PropertyRepository) -> None:
        self.repository = repository
        self.normalizer = PropertyNormalizationService()
        self.validator = PropertyValidationService()
        self.deduplicator = PropertyDeduplicationService(repository)

    @staticmethod
    def quality_score(property_: Property) -> float:
        fields = [property_.title, property_.price, property_.property_type, property_.city,
                  property_.source, property_.source_type, property_.source_id,
                  property_.latitude, property_.longitude, property_.area]
        return round(sum(value is not None and value != "" for value in fields) / len(fields) * 100, 1)

    def ingest(self, raw_records: list[dict[str, Any]], *, source: str, source_type: str) -> IngestionResult:
        if source_type not in {"licensed_feed", "partner_api", "admin", "user", "demo"}:
            raise ValueError("Unsupported property source type")
        result = IngestionResult()
        for raw in raw_records:
            try:
                candidate = self.validator.validate(self.normalizer.normalize(raw, source, source_type))
            except ValidationError:
                result.rejected += 1
                continue
            candidate.data_quality_score = self.quality_score(candidate)
            existing = self.deduplicator.existing(candidate)
            if existing:
                data = candidate.model_dump(exclude={"id"}, exclude_none=True)
                self.repository.update_property(existing.id, data)
                result.updated += 1
            else:
                self.repository.create_property(candidate)
                result.created += 1
        return result
