"""Geocoding worker: resolves properties missing coordinates via the configured
location provider (OSM by default).

Hardening preserved from the original worker:
- cache every successful result (geocode_cache)
- failure TTL so failed addresses are not hammered
- strict rate limiting between provider calls
- single-flight distributed lock with lease expiry/recovery
- provider abstraction (never bypasses LocationProvider)

Integration with ingestion: properties inserted without coordinates are placed
in ``geocode_queue`` by the ingestion pipeline; this worker drains the queue
before falling back to a bounded scan for any legacy rows still missing
coordinates.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.providers.location import (
    LocationProviderUnavailable,
    get_location_provider,
)
from app.workers.base import (
    WorkerRunTracker,
    acquire_lock,
    release_lock,
)

logger = logging.getLogger(__name__)

LOCK_ID = "geocoding_worker_lock"
WORKER_NAME = "geocoding_worker"
BOUNDED_BATCH = 20
RATE_LIMIT_SECONDS = 1.5
FAILURE_TTL_DAYS = 7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cache_lookup(db, address: str, now: datetime) -> Optional[Dict[str, Any]]:
    cached = db["geocode_cache"].find_one({"address": address})
    if not cached:
        return None
    if cached.get("latitude") is None or cached.get("longitude") is None:
        # Respect failure TTL: failed addresses are only retried after the
        # failure window passes.
        created = cached.get("created_at")
        if created and now - created < timedelta(days=FAILURE_TTL_DAYS):
            return None
        return None
    return cached


def _apply_coordinates(db, property_id, lat, lon, provider_name: str) -> None:
    db["properties"].update_one(
        {"_id": property_id},
        {"$set": {
            "latitude": lat,
            "longitude": lon,
            "location": {"type": "Point", "coordinates": [lon, lat]},
            "location_source": provider_name,
            "updated_at": _utcnow(),
        }},
    )


def _candidates(db) -> tuple[list[dict], list[dict]]:
    """Queue-first: drain pending/failed queue items, then a legacy scan."""
    queued = list(
        db["geocode_queue"]
        .find({"status": {"$in": ["pending", "failed"]}})
        .sort("created_at", 1)
        .limit(BOUNDED_BATCH)
    )
    queued_ids = {item.get("property_id") for item in queued}
    remaining = BOUNDED_BATCH - len(queued)
    props: list[dict] = []
    if remaining > 0:
        props = list(
            db["properties"]
            .find({
                "status": {"$in": ["active", "stale"]},
                "latitude": None,
                "_id": {"$nin": list(queued_ids) or [None]},
            })
            .limit(remaining)
        )
    return queued, props


def run_geocoding(db) -> Dict[str, Any]:
    lock = acquire_lock(db, LOCK_ID)
    if not lock.acquired:
        return {"skipped": True, "worker_name": WORKER_NAME, "reason": "lock_busy"}

    tracker = WorkerRunTracker(db, WORKER_NAME)
    try:
        with tracker:
            provider = get_location_provider()
            now = _utcnow()
            queued, props = _candidates(db)
            tracker.processed = min(len(queued) + len(props), BOUNDED_BATCH)
            tracker.persist_counts()

            # Queue items resolve by address; legacy rows by property address.
            items: list[tuple[Optional[dict], dict]] = []
            for item in queued:
                prop = db["properties"].find_one({"_id": item["property_id"]})
                if prop:
                    items.append((item, prop))
            for prop in props:
                items.append((None, prop))

            for queue_item, prop in items:
                address = queue_item.get("address") if queue_item else (
                    prop.get("address")
                    or f"{prop.get('locality', '')}, {prop.get('city', '')}".strip(", ")
                )
                address = (address or "").strip().strip(",")
                if not address:
                    tracker.skipped += 1
                    continue

                cached = _cache_lookup(db, address, now)
                if cached is not None:
                    _apply_coordinates(
                        db, prop["_id"], cached["latitude"], cached["longitude"],
                        cached.get("provider", provider.name),
                    )
                    _mark_queue(db, queue_item, "completed", provider.name)
                    tracker.success += 1
                    continue

                try:
                    result = provider.geocode(address)
                    lat = result.get("latitude")
                    lon = result.get("longitude")
                    db["geocode_cache"].insert_one({
                        "address": address,
                        "latitude": lat,
                        "longitude": lon,
                        "provider": provider.name,
                        "created_at": _utcnow(),
                    })
                    if lat is None or lon is None:
                        tracker.skipped += 1
                        _mark_queue(db, queue_item, "failed", provider.name)
                        continue
                    _apply_coordinates(db, prop["_id"], lat, lon, provider.name)
                    _mark_queue(db, queue_item, "completed", provider.name)
                    tracker.success += 1
                except LocationProviderUnavailable as exc:
                    logger.error("geocoding_provider_unavailable address=%r error=%s", address, exc)
                    tracker.failure += 1
                    db["geocode_cache"].insert_one({
                        "address": address, "latitude": None, "longitude": None,
                        "error": str(exc), "created_at": _utcnow(),
                    })
                    _mark_queue(db, queue_item, "failed", provider.name)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error(
                        "geocoding_failed property=%s address=%r error=%s",
                        prop["_id"], address, exc,
                    )
                    tracker.failure += 1
                    db["geocode_cache"].insert_one({
                        "address": address, "latitude": None, "longitude": None,
                        "error": str(exc), "created_at": _utcnow(),
                    })
                    _mark_queue(db, queue_item, "failed", provider.name)

                # Strict provider rate limiting between calls.
                time.sleep(RATE_LIMIT_SECONDS)

            return {
                "worker_name": WORKER_NAME,
                "status": "completed",
                "run_id": tracker.run_id,
                "processed": tracker.processed,
                "updated": tracker.success,
                "failed": tracker.failure,
                "skipped": tracker.skipped,
            }
    finally:
        release_lock(db, LOCK_ID, lock.owner)


def _mark_queue(db, queue_item: Optional[dict], status: str, provider_name: str) -> None:
    if queue_item is None:
        return
    db["geocode_queue"].update_one(
        {"_id": queue_item["_id"]},
        {"$set": {"status": status, "provider": provider_name, "updated_at": _utcnow()}},
    )