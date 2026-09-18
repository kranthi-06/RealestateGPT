"""Worker scheduler API.

Workers are expensive, state-changing batch jobs. They are triggered either
by:
  1. cron hitting ``POST /api/v1/workers/run/{name}`` with the configured
     ``WORKER_RUN_SECRET`` in the ``X-Worker-Secret`` header (production path,
     works on serverless/cron without an always-on process); or
  2. an admin JWT (bearer token) for manual runs from the admin UI.

``GET /api/v1/workers/status`` exposes provider configuration state and the most
recent run per worker (no secrets; safe for the admin UI and public observability.

Supported workers: property_ingestion, property_refresh, stale_listing_worker,
geocoding_worker, price_history_worker.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_optional_user
from app.models.user import User
from app.schemas import WorkerRunListResponse, WorkerRunResponse, WorkerStatusResponse
from app.workers.base import latest_runs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workers", tags=["Workers"])

WORKER_FUNCTIONS = {
    "property_ingestion": ("app.workers.ingestion", "run_property_ingestion"),
    "property_refresh": ("app.workers.refresh", "run_property_refresh"),
    "stale_listing_worker": ("app.workers.stale", "run_stale_detection"),
    "geocoding_worker": ("app.workers.geocoding", "run_geocoding"),
    "price_history_worker": ("app.workers.price_history", "run_price_history_normalizer"),
}


def _verify_secret(worker_secret: Optional[str], admin: Optional[User]) -> bool:
    if admin is not None:
        return True
    expected = (settings.WORKER_RUN_SECRET or "").strip()
    secret = (worker_secret or "").strip()
    if not expected or not secret:
        return False
    return hmac.compare_digest(secret, expected)


async def _optional_admin(user: Optional[User] = Depends(get_optional_user)) -> Optional[User]:
    """Admin only counts as admin (never a client-supplied role flag)."""
    if user is not None and user.role == "admin":
        return user
    return None


@router.post("/run/{worker_name}")
async def run_worker(
    worker_name: str,
    db = Depends(get_db),
    x_worker_secret: Optional[str] = Header(None, alias="X-Worker-Secret"),
    admin: Optional[User] = Depends(_optional_admin),
):
    """Trigger a worker run. Requires the worker secret (cron path) or an
    admin bearer token (manual path). Runs inline in a thread (no event-loop
    blocking), returns the run summary."""
    if worker_name not in WORKER_FUNCTIONS:

        raise HTTPException(status_code=404, detail=f"Unknown worker: {worker_name}")

    if not _verify_secret(x_worker_secret, admin=admin):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid worker secret. Set X-Worker-Secret or use an admin token.",
        )

    module_name, function_name = WORKER_FUNCTIONS[worker_name]
    try:
        module = __import__(module_name, fromlist=[function_name])
        fn = getattr(module, function_name)
        result = await asyncio.to_thread(fn, db)
    except Exception:
        logger.exception("worker_trigger_failed worker=%s", worker_name)
        raise HTTPException(status_code=502, detail="Worker execution failed. Check backend logs.")

    return _record_run(worker_name, result)


@router.get("/status", response_model=WorkerStatusResponse)
async def worker_status(db = Depends(get_db)):
    """Provider/worker availability state (no secrets). Safe for admin UI."""
    from app.providers.property import (
        get_property_provider,
        provider_configuration_error,
    )

    provider = get_property_provider()
    configured = provider.name != "not_configured"

    last_runs: Dict[str, Any] = {}
    for name in WORKER_FUNCTIONS:

        rows = latest_runs(db, name, limit=1)
        if rows:
            row = rows[0]
            last_runs[name] = {
                key: row.get(key) for key in (
                    "status", "started_at", "processed_count", "success_count",
                    "failure_count", "skipped_count", "error_summary",
                )
            }
    return WorkerStatusResponse(
        property_provider=provider.name if configured else "",
        property_provider_configured=configured,
        provider_message=None if configured else provider_configuration_error(),
        location_provider=settings.LOCATION_PROVIDER,
        last_runs=last_runs,
    )


@router.get("/runs", response_model=WorkerRunListResponse)
async def worker_runs(
    worker_name: str = Query(..., description="Worker name"),
    limit: int = Query(10, ge=1, le=50),
    db = Depends(get_db),
    current_user: User = Depends(_optional_admin),
):
    """Recent worker_runs for admin monitoring. Admin-only."""
    if current_user is None:
        raise HTTPException(status_code=403, detail="Admin access required")
    rows = latest_runs(db, worker_name, limit=limit)
    skip_keys = {
        "_id", "worker_name", "run_id", "status", "started_at", "completed_at",
        "duration_ms", "processed_count", "success_count", "failure_count",
        "skipped_count", "error_summary",
    }
    runs = []
    for row in rows:
        runs.append(WorkerRunResponse(
            worker_name=row.get("worker_name", worker_name),
            run_id=row.get("run_id", ""),
            status=row.get("status", "unknown"),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            duration_ms=row.get("duration_ms"),
            processed_count=row.get("processed_count", 0),
            success_count=row.get("success_count", 0),
            failure_count=row.get("failure_count", 0),
            skipped_count=row.get("skipped_count", 0),
            error_summary=row.get("error_summary"),
            extra={k: v for k, v in row.items() if k not in skip_keys and v is not None},
        ))
    return WorkerRunListResponse(runs=runs, total=len(runs))


def _record_run(worker_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    if result.get("skipped"):
        return {
            "worker_name": worker_name,
            "status": "skipped",
            "run_id": result.get("run_id"),
            "reason": result.get("reason"),
            "message": result.get("error_summary"),
        }
    return {
        "worker_name": worker_name,
        "status": result.get("status", "completed"),
        "run_id": result.get("run_id"),
        "processed": result.get("processed", result.get("processed_count", 0)),
        "success": result.get("success", result.get("updated", 0)),
        "failure": result.get("failure", result.get("failed", 0) or result.get("rejected", 0)),
        "skipped": result.get("skipped", 0),
        "added": result.get("added"),
        "updated": result.get("updated"),
        "created": result.get("created_count"),
    }
