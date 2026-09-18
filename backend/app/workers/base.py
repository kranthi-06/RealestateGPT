"""Worker primitives: distributed lock with lease expiry/recovery and run
tracking that persists to ``worker_runs``.

Locking model
-------------
``worker_locks`` holds one document per worker::

    {"_id": "<worker>_lock", "locked_until": <datetime>, "owner": "<uuid>"}

* ``acquire_lock`` uses an atomic upsert so two processes can never both hold
  the lock.
* A crashed worker leaves ``locked_until`` in the future; the lease expires
  after ``WORKER_LOCK_TTL_SECONDS`` and the next run reclaims it
  (lock recovery).
* ``release_lock`` only releases when the caller's owner token still matches,
  so one worker can never rescind another worker's lease.

Run tracking
------------
``WorkerRunTracker`` records every run (including failures and crashes) with
processed/success/failure/skipped counts and duration, powering the admin
monitoring page and observability tooling.
"""
from __future__ import annotations

import contextvars
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_run_event_id: contextvars.ContextVar[str] = contextvars.ContextVar("worker_run_id", default="")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def worker_run_id() -> str:
    """The run id of the currently executing worker (empty outside workers)."""
    return _run_event_id.get()


@dataclass
class LockResult:
    acquired: bool = False
    owner: str = ""


def acquire_lock(db, lock_id: str, ttl_seconds: Optional[int] = None) -> LockResult:
    """Try to acquire (or reclaim) a worker lock. Never blocks."""
    ttl = ttl_seconds or settings.WORKER_LOCK_TTL_SECONDS
    owner = uuid.uuid4().hex
    now = _utcnow()
    locks = db["worker_locks"]

    # Fast path: brand-new lock document.
    try:
        locks.insert_one({"_id": lock_id, "locked_until": now, "owner": owner})
        return LockResult(acquired=True, owner=owner)
    except Exception:
        pass  # DuplicateKeyError -> fall through to lease check

    # Lease path: reclaim when expired OR (defensive) when the owner died.
    reclaimed = locks.find_one_and_update(
        {
            "_id": lock_id,
            "locked_until": {"$lt": now},
        },
        {
            "$set": {
                "locked_until": now + timedelta(seconds=ttl),
                "owner": owner,
                "recovered": True,
            }
        },
    )
    if reclaimed is not None:
        logger.warning("worker_lock_recovered lock=%s", lock_id)
        return LockResult(acquired=True, owner=owner)

    # Locked to completion by another process.
    holder = locks.find_one({"_id": lock_id})
    logger.info(
        "worker_lock_busy lock=%s held_until=%s",
        lock_id,
        holder.get("locked_until") if holder else "unknown",
    )
    return LockResult(acquired=False, owner="")


def release_lock(db, lock_id: str, owner: str) -> bool:
    """Release the lock only if we still own it. Idempotent."""
    result = db["worker_locks"].find_one_and_update(
        {"_id": lock_id, "owner": owner},
        {"$set": {"locked_until": datetime.fromtimestamp(0, tz=timezone.utc), "owner": ""}},
    )
    return result is not None


@dataclass
class WorkerRunTracker:
    """Records a worker execution in ``worker_runs``.

    Use as a context manager::

        with WorkerRunTracker(db, "property_ingestion") as run:
            run.processed = 10
            run.success = 7
            # ... on exception, run is persisted as failed with the error summary
    """

    db: Any
    worker_name: str
    error_summary: str = ""
    start_time: float = field(default_factory=time.perf_counter)
    started_at: Optional[datetime] = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    # Counters (populated by the worker)
    processed: int = 0
    success: int = 0
    failure: int = 0
    skipped: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    # Written on finish
    status: str = "running"
    completed_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        self.started_at = self.started_at or _utcnow()
        _run_event_id.set(self.run_id)
        self.db["worker_runs"].insert_one(self._document("running"))

    def _document(self, status: str) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "worker_name": self.worker_name,
            "run_id": self.run_id,
            "status": status,
            "started_at": self.started_at,
            "processed_count": self.processed,
            "success_count": self.success,
            "failure_count": self.failure,
            "skipped_count": self.skipped,
            "error_summary": self.error_summary,
        }
        if self.completed_at is not None:
            doc["completed_at"] = self.completed_at
            doc["duration_ms"] = round(
                (self.completed_at - self.started_at).total_seconds() * 1000, 1
            )
        doc.update(self.extra)
        return doc

    def persist_counts(self) -> None:
        self.db["worker_runs"].update_one(
            {"run_id": self.run_id},
            {"$set": {
                "processed_count": self.processed,
                "success_count": self.success,
                "failure_count": self.failure,
                "skipped_count": self.skipped,
            }},
        )

    def finish(self, status: str = "completed", error_summary: str = "") -> None:
        self.status = status
        self.error_summary = error_summary or self.error_summary
        self.completed_at = _utcnow()
        self.db["worker_runs"].update_one(
            {"run_id": self.run_id},
            {"$set": self._document(status)},
        )

    def __enter__(self) -> "WorkerRunTracker":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None:
            self.finish("failed", error_summary=str(exc)[:500])
            logger.error(
                "worker_failed worker=%s run=%s error=%s",
                self.worker_name, self.run_id, exc, exc_info=exc,
            )
            return False  # propagate
        self.finish("completed")
        logger.info(
            "worker_completed worker=%s run=%s processed=%s success=%s failure=%s skipped=%s",
            self.worker_name, self.run_id,
            self.processed, self.success, self.failure, self.skipped,
        )
        return False


def latest_runs(db, worker_name: str, limit: int = 1) -> list[dict[str, Any]]:
    """Most recent worker_runs records for a worker (admin monitoring)."""
    cursor = (
        db["worker_runs"]
        .find({"worker_name": worker_name})
        .sort("started_at", -1)
        .limit(limit)
    )
    return list(cursor)