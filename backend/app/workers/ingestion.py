"""Property ingestion worker: Provider -> Fetch -> Normalize -> Validate ->
Deduplicate -> Publish -> Geocode eligibility -> freshness.

Idempotency: ingesting the same listing twice never creates a duplicate; the
deduplication engine routes repeat sightings to the existing document.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.repositories.property_repo import PropertyRepository
from app.services.property_ingestion_service import PropertyIngestionService
from app.providers.property import get_property_provider
from app.workers.base import (
    WorkerRunTracker,
    acquire_lock,
    release_lock,
)

logger = logging.getLogger(__name__)

LOCK_ID = "property_ingestion_lock"
WORKER_NAME = "property_ingestion"


async def _collect_records(provider, tracker: WorkerRunTracker) -> list[dict[str, Any]]:
    """Fetch a bounded batch of records with cursor pagination."""
    records: list[dict[str, Any]] = []
    cursor: Optional[str] = None
    pages = 0
    while len(records) < settings.INGESTION_BATCH_SIZE and pages < settings.INGESTION_MAX_PAGES:
        batch, cursor = await provider.fetch_properties(cursor)
        records.extend(batch or [])
        pages += 1
        if not cursor:
            break
    return records


def run_property_ingestion(db, *, source: Optional[str] = None, source_type: Optional[str] = None) -> Dict[str, Any]:
    """Execute one ingestion pass. Returns a summary dict (also recorded in
    ``worker_runs``). Safe to call from cron, the scheduler API, or tests."""
    lock = acquire_lock(db, LOCK_ID)
    if not lock.acquired:
        logger.info("property_ingestion skipped: another run holds the lock")
        return {"skipped": True, "worker_name": WORKER_NAME, "reason": "lock_busy"}

    tracker = WorkerRunTracker(db, WORKER_NAME)
    try:
        with tracker:
            provider = get_property_provider()
            if isinstance(provider, type(None)) or provider.name == "not_configured":
                tracker.skipped = 1
                tracker.extra["error_summary"] = (
                    "No property provider configured; inventory intentionally empty."
                )
                return _summary(tracker, status="skipped")

            effective_source = source or provider.name
            effective_type = source_type or provider.source_type

            records = asyncio.run(_collect_records(provider, tracker))
            tracker.processed = len(records)
            tracker.persist_counts()

            service = PropertyIngestionService(PropertyRepository(db))
            result = service.ingest(records, source=effective_source, source_type=effective_type)

            tracker.success = result.created + result.updated + result.duplicates
            tracker.failure = result.failed + result.rejected
            tracker.extra["created_count"] = result.created
            tracker.extra["updated_count"] = result.updated
            tracker.extra["duplicates_count"] = result.duplicates
            tracker.extra["rejected_count"] = result.rejected
            tracker.extra["reviews_count"] = result.reviews
            if result.rejection_reasons:
                tracker.extra["rejection_reasons"] = result.rejection_reasons
            return _summary(tracker, result=result)
    finally:
        release_lock(db, LOCK_ID, lock.owner)


def _summary(tracker: WorkerRunTracker, result=None, status: str = "completed") -> Dict[str, Any]:
    summary = {
        "worker_name": WORKER_NAME,
        "status": status,
        "run_id": tracker.run_id,
        "processed": tracker.processed,
        "success": tracker.success,
        "failure": tracker.failure,
        "skipped": tracker.skipped,
        "started_at": tracker.started_at.isoformat() if tracker.started_at else None,
        "completed_at": tracker.completed_at.isoformat() if tracker.completed_at else None,
    }
    if result is not None:
        summary.update({
            "added": result.created,
            "updated": result.updated,
            "duplicates": result.duplicates,
            "failed": result.failed,
            "rejected": result.rejected,
            "reviews": result.reviews,
        })
    if tracker.extra:
        summary.update(tracker.extra)
    return summary