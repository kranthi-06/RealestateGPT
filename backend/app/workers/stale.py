"""Stale listing worker: active -> stale -> expired/inactive.

Uses configured thresholds:
  LISTING_STALE_AFTER_HOURS — no provider sighting (last_seen_at) for this long
                              -> status "stale", stale_at set once.
  LISTING_EXPIRE_AFTER_DAYS — stale for this long -> status "expired" and
                              soft-deactivated (never shown as fresh/available).

Stale and expired listings stay in the database for history; only the search
query (status == "active", is_active) keeps them out of new results.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from app.core.config import settings
from app.workers.base import (
    WorkerRunTracker,
    acquire_lock,
    release_lock,
)

logger = logging.getLogger(__name__)

LOCK_ID = "stale_listing_lock"
WORKER_NAME = "stale_listing_worker"


def run_stale_detection(db) -> Dict[str, Any]:
    lock = acquire_lock(db, LOCK_ID)
    if not lock.acquired:
        return {"skipped": True, "worker_name": WORKER_NAME, "reason": "lock_busy"}

    tracker = WorkerRunTracker(db, WORKER_NAME)
    try:
        with tracker:
            now = datetime.now(timezone.utc)
            stale_after = now - timedelta(hours=settings.LISTING_STALE_AFTER_HOURS)
            expire_after = now - timedelta(days=settings.LISTING_EXPIRE_AFTER_DAYS)

            # 1) active -> stale
            stale_cursor = db["properties"].find({
                "status": "active",
                "is_active": True,
                "last_seen_at": {"$lt": stale_after},
            })
            stale_ids: list[int] = []
            for prop in stale_cursor:
                stale_ids.append(prop["_id"])
                try:
                    db["properties"].update_one(
                        {"_id": prop["_id"], "status": "active"},
                        {"$set": {
                            "status": "stale",
                            "stale_at": prop.get("stale_at") or now,
                            "updated_at": now,
                        }},
                    )
                    tracker.success += 1
                except Exception as exc:
                    tracker.failure += 1
                    logger.warning("stale_update_failure property=%s error=%s", prop["_id"], exc)

            # 2) stale -> expired (long absence)
            expire_cursor = db["properties"].find({
                "status": "stale",
                "is_active": True,
                "stale_at": {"$lt": expire_after},
            })
            expired = 0
            for prop in expire_cursor:
                try:
                    db["properties"].update_one(
                        {"_id": prop["_id"], "status": "stale"},
                        {"$set": {
                            "status": "expired",
                            "expired_at": prop.get("expired_at") or now,
                            "is_active": False,
                            "updated_at": now,
                        }},
                    )
                    expired += 1
                    tracker.success += 1
                except Exception as exc:
                    tracker.failure += 1
                    logger.warning("expire_update_failure property=%s error=%s", prop["_id"], exc)

            tracker.processed = len(stale_ids) + expired
            tracker.extra["stale_count"] = len(stale_ids)
            tracker.extra["expired_count"] = expired
            return {
                "worker_name": WORKER_NAME,
                "status": "completed",
                "run_id": tracker.run_id,
                "stale": len(stale_ids),
                "expired": expired,
                "processed": tracker.processed,
                "success": tracker.success,
                "failure": tracker.failure,
            }
    finally:
        release_lock(db, LOCK_ID, lock.owner)