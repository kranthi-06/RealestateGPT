"""Explicit promotion of web discoveries into the property catalogue.

Web discoveries are search-provider-backed hypotheses, deliberately kept out of
the catalogue by the discovery pipeline ("never automatically promoted"). This
module is the authorized, explicit promotion path an operator can run (via the
admin endpoint or a script). It is honest by construction:

* only the fields the discovery actually recorded are copied — no prices,
  coordinates, addresses or distances are invented;
* promoted records are marked ``source_type="web_discovery"``,
  ``is_synthetic=False`` and stay ``verification_status="unverified"`` —
  they are real-world listings found on the web, not verified inventory;
* records without a determinable property type are skipped rather than
  guessed into a canonical type;
* ingestion runs through the standard pipeline (validate -> normalize ->
  deduplicate -> publish), so promotion is idempotent per source listing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories.property_repo import PropertyRepository
from app.services.property_ingestion_service import PropertyIngestionService

PROMOTION_SOURCE = "web_discovery"
PROMOTION_SOURCE_TYPE = "web_discovery"

# Discovery categories that name their own property type.
_CATEGORY_PROPERTY_TYPE = {
    "HOTEL": "hotel",
    "VACATION_RENTAL": "vacation_rental",
}

# Categories that are residential have no type field; the type is only taken
# from explicit wording in the listing's own title. Anything else is skipped.
_TITLE_TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("apartment", r"\b(apartment|apartments|flat|flats)\b"),
    ("villa", r"\b(villa|villas|independent house|duplex)\b"),
    ("plot", r"\b(plot|plots|land)\b"),
    ("house", r"\b(house|houses|home)\b"),
    ("commercial", r"\b(office|commercial|shop|showroom|warehouse)\b"),
    ("pg", r"\b(pg|paying guest|hostel)\b"),
)

_RENT_CATEGORIES = {"PROPERTY_RENT", "VACATION_RENTAL", "HOTEL"}
_ALLOWED_AREA_UNITS = {"sqft", "sqm", "acre", "hectare"}


@dataclass
class PromotionSummary:
    fetched: int = 0
    promoted: int = 0
    skipped: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)

    def _skip(self, reason: str) -> None:
        self.skipped += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1


def _infer_property_type(discovery: dict[str, Any]) -> Optional[str]:
    """Property type from the discovery's own category/title, else None."""
    mapped = _CATEGORY_PROPERTY_TYPE.get(str(discovery.get("category") or "").upper())
    if mapped:
        return mapped
    title = str(discovery.get("title") or "").lower()
    for label, pattern in _TITLE_TYPE_PATTERNS:
        if re.search(pattern, title):
            return label
    return None


def _infer_listing_type(discovery: dict[str, Any]) -> str:
    category = str(discovery.get("category") or "").upper()
    if category in _RENT_CATEGORIES:
        return "rent"
    if str(discovery.get("transaction_type") or "").lower() in ("rent", "rental", "lease"):
        return "rent"
    return "sale"


def map_discovery_to_record(discovery: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Translate a web-discovery document into a canonical property payload.

    Returns ``None`` when the record cannot be mapped without inventing data
    (no price, no city, no determinable property type, or an unusable title).
    """
    title = str(discovery.get("title") or "").strip()
    if len(title) < 5 or len(title) > 500:
        return None

    price = discovery.get("normalized_price") or discovery.get("price")
    if not price or float(price) <= 0:
        return None

    city = str(discovery.get("city") or "").strip()
    if not city:
        return None

    property_type = _infer_property_type(discovery)
    if not property_type:
        return None

    listing_type = _infer_listing_type(discovery)
    source_listing_id = str(discovery.get("_id") or "").strip()
    if not source_listing_id:
        return None

    record: dict[str, Any] = {
        "title": title,
        "price": float(price),
        "property_type": property_type,
        "listing_type": listing_type,
        "transaction_type": listing_type,
        "city": city[:100],
        "source": PROMOTION_SOURCE,
        "source_type": PROMOTION_SOURCE_TYPE,
        "source_url": str(discovery.get("result_url") or "")[:2_000] or None,
        "source_listing_id": source_listing_id,
        "source_id": source_listing_id,
        "status": "active",
    }

    currency = str(discovery.get("normalized_currency") or discovery.get("currency") or "INR").upper()
    record["currency"] = currency[:3] if len(currency) >= 3 else "INR"

    description = discovery.get("description")
    if description:
        record["description"] = str(description)[:10_000]

    for field_name in (
        "bedrooms", "bathrooms", "parking", "floor", "total_floors",
        "area", "area_sqft", "locality", "furnishing", "builder_name",
    ):
        value = discovery.get(field_name)
        if value is not None and value != "":
            record[field_name] = value

    area_unit = str(discovery.get("area_unit") or "").lower()
    if area_unit in _ALLOWED_AREA_UNITS:
        record["area_unit"] = area_unit

    address = discovery.get("location_text")
    if address:
        record["address"] = str(address)[:500]

    # Coordinates are copied only when the discovery recorded them. Missing
    # coordinates stay missing: the geocoding worker resolves them from real
    # addresses, and nothing is ever interpolated here.
    latitude, longitude = discovery.get("latitude"), discovery.get("longitude")
    if latitude is not None and longitude is not None:
        record["latitude"] = float(latitude)
        record["longitude"] = float(longitude)
        location_source = discovery.get("location_source")
        if location_source:
            record["location_source"] = str(location_source)[:50]

    image_url = discovery.get("image_url")
    if image_url and str(image_url).startswith(("http://", "https://")):
        record["images"] = [{"url": str(image_url)[:2_000], "display_order": 0}]

    amenities = discovery.get("amenities")
    if isinstance(amenities, list):
        cleaned = [str(a) for a in amenities if a]
        if cleaned:
            record["amenities"] = cleaned

    return record


def promote_web_discoveries(
    db,
    *,
    limit: int = 200,
    min_confidence: float = 0.0,
    now: Optional[datetime] = None,
) -> PromotionSummary:
    """Promote live, mappable discoveries into the catalogue (idempotent)."""
    moment = now or datetime.now(timezone.utc)
    repository = PropertyRepository(db)
    ingestion = PropertyIngestionService(repository)

    summary = PromotionSummary()
    cursor = (
        db["web_property_discoveries"]
        .find({"expires_at": {"$gt": moment}})
        .sort("discovered_at", -1)
        .limit(limit)
    )
    records: list[dict[str, Any]] = []
    for discovery in cursor:
        summary.fetched += 1
        if float(discovery.get("confidence") or 0.0) < min_confidence:
            summary._skip("low_confidence")
            continue
        record = map_discovery_to_record(discovery)
        if record is None:
            summary._skip("unmappable")
            continue
        records.append(record)

    if records:
        result = ingestion.ingest(
            records, source=PROMOTION_SOURCE, source_type=PROMOTION_SOURCE_TYPE
        )
        summary.promoted = result.created + result.updated + result.duplicates
        for reason, count in result.rejection_reasons.items():
            summary.skipped += count
            summary.skip_reasons[f"ingest_rejected:{reason}"] = count
        summary.skip_reasons.setdefault("ingest_failed", result.failed)
        if result.failed:
            summary.skipped += result.failed
    return summary
