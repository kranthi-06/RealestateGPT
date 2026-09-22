"""Web discovery cleanup worker.

Responsibilities:
* remove expired web_search_cache entries
* remove expired web_property_discoveries records (TTL index is the primary
  mechanism; this worker cleans any residue and keeps high-volume tables small)
* never touches canonical ``properties``

Uses the standard distributed lock + run tracking; safe to trigger via cron or
the protected workers API.
"""
from __future__ import annotations

import logging
from typing import Dict

from app.discovery.cache import WebSearchCacheRepository
from app.discovery.repository import WebDiscoveryRepository
from app.workers.base import (
    WorkerRunTracker,
    acquire_lock,
    release_lock,
)

logger = logging.getLogger(__name__)

LOCK_ID = "web_discovery_cleanup_lock"
WORKER_NAME = "web_discovery_cleanup"


def run_web_discovery_cleanup(db) -> Dict[str, Any]:
    lock = acquire_lock(db, LOCK_ID)
    if not lock.acquired:
        return {"skipped": True, "worker_name": WORKER_NAME, "reason": "lock_busy"}

    tracker = WorkerRunTracker(db, WORKER_NAME)
    try:
        with tracker:
            cache_removed = WebSearchCacheRepository(db).cleanup()
            tracker.processed += cache_removed

            discovery_removed = WebDiscoveryRepository(db).cleanup()
            tracker.processed += discovery_removed
            tracker.success = cache_removed + discovery_removed

            # Sweep orphaned temporary records with no expiry but older than
            # the discovery TTL window (defensive; expiry remains authoritative).
            stale = db["web_property_discoveries"].count_documents(
                {"expires_at": None, "discovered_at": None}
            )
            tracker.extra["legacy_unnormalized"] = stale
            return {
                "worker_name": WORKER_NAME,
                "status": "completed",
                "run_id": tracker.run_id,
                "processed": tracker.processed,
                "cache_removed": cache_removed,
                "discovery_removed": discovery_removed,
                "success": tracker.success,
                "failure": tracker.failure,
                "skipped": tracker.skipped,
            }
    finally:
        release_lock(db, LOCK_ID, lock.owner)