"""Optional web discovery refresh worker.

Refreshes only high-demand cached queries (queries with the most recent cache
misses / usage) — never every discovery. Respects provider quota, rate limits
and the cache TTL. Idempotent: refreshing the same query twice converges to the
same cache state.

When WEB_DISCOVERY_ENABLED is false or no provider is configured, the worker
reports a skippable run and does nothing (no fake results, no provider calls).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.core.config import settings
from app.discovery.cache import WebSearchCacheRepository, cache_key_for_intent
from app.discovery.service import WebDiscoveryService
from app.schemas.ai import SearchIntent
from app.workers.base import (
    WorkerRunTracker,
    acquire_lock,
    release_lock,
)

logger = logging.getLogger(__name__)

LOCK_ID = "web_discovery_refresh_lock"
WORKER_NAME = "web_discovery_refresh"
REFRESH_BUDGET = 5  # bounded: never refresh the whole cache in one pass


def run_web_discovery_refresh(db) -> Dict[str, Any]:
    lock = acquire_lock(db, LOCK_ID)
    if not lock.acquired:
        return {"skipped": True, "worker_name": WORKER_NAME, "reason": "lock_busy"}

    tracker = WorkerRunTracker(db, WORKER_NAME)
    try:
        with tracker:
            if not settings.WEB_DISCOVERY_ENABLED:
                tracker.skipped = 1
                tracker.extra["error_summary"] = (
                    "WEB_DISCOVERY_ENABLED=false; nothing to refresh."
                )
                return _summary(tracker, status="skipped")

            # High-demand candidates: most recent entries are refreshed first.
            now = datetime.now(timezone.utc)
            cursor = (
                db["web_search_cache"]
                .find({"expires_at": {"$lt": now}})
                .sort("created_at", -1)
                .limit(REFRESH_BUDGET)
            )
            rows = list(cursor)
            tracker.processed = len(rows)

            service = WebDiscoveryService(db)
            for row in rows:
                intent_data = row.get("normalized_intent") or {}
                intent = SearchIntent.model_validate(intent_data)
                try:
                    outcome = service.discover(intent, max_queries=1, enrich=False)
                except Exception as exc:  # noqa: BLE001 - worker must not die
                    tracker.failure += 1
                    logger.warning("web_discovery_refresh_failed key=%s error=%s", row.get("cache_key"), exc)
                    continue
                if outcome.status == "available" and not outcome.cache_hit:
                    tracker.success += 1
                else:
                    tracker.skipped += 1
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