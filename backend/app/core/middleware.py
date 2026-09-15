"""RealEstateGPT - Request context middleware.

Generates (or honours) a ``X-Request-ID`` header for every request, logs
endpoint/latency/status for observability and keeps the id available to all
logged records through ``app.core.logging.request_id_var``.

No credentials or sensitive request bodies are ever logged.
"""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        supplied = request.headers.get("X-Request-ID")
        request_id = supplied.strip()[:64] if supplied and supplied.strip() else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info(
                "http_request method=%s path=%s status=%s latency_ms=%s",
                request.method, request.url.path, status, latency_ms,
            )
            request_id_var.reset(token)