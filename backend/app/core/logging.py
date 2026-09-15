"""RealEstateGPT - Structured logging and request correlation.

Every log record is correlated to the current HTTP request through a
context variable. The request id can be provided by an upstream proxy
(``X-Request-ID``) or generated inside the application middleware.

Usage:

    from app.core.logging import get_request_id  # or rely on the middleware filter

All logging is performed with ``logging.getLogger(__name__)``; no record is
ever written to stdout directly (the previous ``print()`` debug paths have
been removed).
"""
from __future__ import annotations

import contextvars
import logging
import sys

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the request id for the current request context (if any)."""
    return request_id_var.get()


class RequestIdFilter(logging.Filter):
    """Attach the active request id to every log record as ``request_id``."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging(debug: bool = False) -> None:
    """Configure structured logging once for the whole process."""
    fmt = "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    # Replace pre-existing root handlers so the filter applies everywhere.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)