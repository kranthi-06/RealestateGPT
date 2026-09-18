"""Price-history normalization worker.

Backfills and validates ``price_history`` documents and computes per-property
price summaries that power the price-intelligence UI. Runs idempotently; never
invents history that was not observed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.workers.base import (
    WorkerRunTracker,
    acquire_lock,
    release_lock,
)

logger = logging.getLogger(__name__)

LOCK_ID = "price_history_lock"
WORKER_NAME = "price_history_worker"


def run_price_history_normalizer(db) -> Dict[str, Any]:
    lock = acquire_lock(db, LOCK_ID)
    if not lock.acquired:
        return {"skipped": True, "worker_name": WORKER_NAME, "reason": "lock_busy"}

    tracker = WorkerRunTracker(db, WORKER_NAME)
    try:
        with tracker:
            now = datetime.now(timezone.utc)
            normalised = 0
            summarized = 0

            # 1) Ensure every history record has a change_type and timestamp.
            for record in db["price_history"].find({}):
                tracker.processed += 1
                updates: Dict[str, Any] = {}
                if not record.get("changed_at"):
                    updates["changed_at"] = record.get("created_at") or now
                if not record.get("change_type"):
                    old = record.get("old_price")
                    new = record.get("new_price")
                    if old and new and old != new:
                        updates["change_type"] = "price_increased" if new > old else "price_decreased"
                    else:
                        updates["change_type"] = "initial_listing"
                if updates:
                    db["price_history"].update_one(
                        {"_id": record["_id"]}, {"$set": updates}
                    )
                    normalised += 1

            # 2) Compute per-property summaries (current/previous/pct/observations).
            properties = db["properties"].find({})
            for prop in properties:
                history_rows = list(
                    db["price_history"]
                    .find({"property_id": prop["_id"]})
                    .sort("changed_at", -1)
                    .limit(50)
                )
                if not history_rows:
                    continue
                current = float(prop.get("price") or 0)
                previous = None
                for row in history_rows:
                    value = float(row.get("new_price") or 0)
                    if value and abs(value - current) > 0.01:
                        previous = value
                        break
                pct_change = None
                if previous:
                    pct_change = round((current - previous) / previous * 100, 2)
                summary = {
                    "observations": len(history_rows),
                    "previous_price": previous,
                    "price_change_pct": pct_change,
                }
                db["properties"].update_one(
                    {"_id": prop["_id"]},
                    {"$set": {"price_intelligence": summary, "updated_at": now}},
                )
                summarized += 1

            tracker.success = tracked_success = normalised + summarized
            tracker.extra["normalised"] = normalised
            tracker.extra["summarized"] = summarized
            return {
                "worker_name": WORKER_NAME,
                "status": "completed",
                "run_id": tracker.run_id,
                "processed": tracker.processed,
                "normalised": normalised,
                "summarized": summarized,
                "success": tracked_success,
                "failure": tracker.failure,
            }
    finally:
        release_lock(db, LOCK_ID, lock.owner)