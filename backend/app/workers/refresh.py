"""Listing refresh worker: re-verify every active listing with the provider.

Lifecycle rules (never guess market status):
* provider returns a record      -> update fields, bump last_seen_at +
  last_verified_at, reset stale/expired markers, keep active.
* provider confirms terminal     -> status sold/rented/inactive per record.
* provider fails/not configured  -> count the failure; DO NOT mark inactive.
  (Provider failure is not the same as an unavailable property.)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import settings
from app.repositories.property_repo import PropertyRepository
from app.services.property_ingestion_service import PropertyIngestionService
from app.providers.property import (
    ProviderListingNotFoundError,
    ProviderNotConfiguredError,
    ProviderUnavailableError,
    get_property_provider,
)
from app.workers.base import (
    WorkerRunTracker,
    acquire_lock,
    release_lock,
)

logger = logging.getLogger(__name__)

LOCK_ID = "property_refresh_lock"
WORKER_NAME = "property_refresh"
REFRESH_BATCH = 50


async def _refresh_one(provider, listing_id: str) -> Dict[str, Any]:
    return await provider.refresh(listing_id)


def run_property_refresh(db, *, limit: Optional[int] = None) -> Dict[str, Any]:
    """Re-verify active listings. Only provider-confirmed states are terminal."""
    lock = acquire_lock(db, LOCK_ID)
    if not lock.acquired:
        return {"skipped": True, "worker_name": WORKER_NAME, "reason": "lock_busy"}

    tracker = WorkerRunTracker(db, WORKER_NAME)
    try:
        with tracker:
            provider = get_property_provider()
            if provider.name == "not_configured":
                tracker.skipped = 1
                tracker.extra["error_summary"] = (
                    "No property provider configured; nothing to refresh."
                )
                return _summary(tracker, status="skipped")

            now = datetime.now(timezone.utc)
            query = {"is_active": True, "status": "active"}
            docs = list(
                db["properties"]
                .find(query)
                .sort("last_verified_at", 1)
                .limit(limit or REFRESH_BATCH)
            )
            tracker.processed = len(docs)
            tracker.persist_counts()
            repo = PropertyRepository(db)
            service = PropertyIngestionService(repo)
            provider_failures = 0

            for doc in docs:
                listing_id = doc.get("source_listing_id") or doc.get("source_id")
                if not listing_id:
                    # No provider identity: keep as-is but age the verification.
                    db["properties"].update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"last_verified_at": now, "updated_at": now}},
                    )
                    tracker.skipped += 1
                    continue
                try:
                    record = asyncio.run(_refresh_one(provider, listing_id))
                except ProviderListingNotFoundError:
                    # Provider is reachable but stopped returning the listing.
                    db["properties"].update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"last_seen_at": now, "updated_at": now}},
                    )
                    tracker.skipped += 1
                    continue
                except (ProviderUnavailableError, ProviderNotConfiguredError, Exception) as exc:
                    provider_failures += 1
                    tracker.failure += 1
                    logger.warning(
                        "refresh_failure property=%s listing=%s error=%s",
                        doc["_id"], listing_id, exc,
                    )
                    continue

                confirmed_status = str(record.get("status") or "active").lower()
                if confirmed_status in ("sold", "rented", "inactive", "expired", "removed"):
                    db["properties"].update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "status": confirmed_status,
                            "last_seen_at": now,
                            "last_verified_at": now,
                            "updated_at": now,
                        }},
                    )
                    tracker.success += 1
                    tracker.extra.setdefault("status_changes", {})[confirmed_status] = (
                        tracker.extra.get("status_changes", {}).get(confirmed_status, 0) + 1
                    )
                    continue

                # Live sighting -> full refresh through the ingestion pipeline.
                record.pop("status", None)
                try:
                    service.ingest([record], source=provider.name, source_type=provider.source_type)
                    tracker.success += 1
                except Exception as exc:
                    tracker.failure += 1
                    logger.warning("refresh_ingest_failure property=%s error=%s", doc["_id"], exc)

            tracker.extra["provider_failures"] = provider_failures
            return _summary(tracker)
    finally:
        release_lock(db, LOCK_ID, lock.owner)


def _summary(tracker: WorkerRunTracker, status: str = "completed") -> Dict[str, Any]:
    return {
        "worker_name": WORKER_NAME,
        "status": status,
        "run_id": tracker.run_id,
        "processed": tracker.processed,
        "success": tracker.success,
        "failure": tracker.failure,
        "skipped": tracker.skipped,
        "started_at": tracker.started_at.isoformat() if tracker.started_at else None,
        "completed_at": tracker.completed_at.isoformat() if tracker.completed_at else None,
        **tracker.extra,
    }