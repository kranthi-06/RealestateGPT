"""RealEstateGPT - Centralized error codes and typed application exceptions.

Every error returned to the client carries a machine-readable ``code`` and a
safe ``message`` that never leaks internal state.  Modules raise these instead
of bare ``HTTPException`` so the global handler in ``main.py`` can produce
uniform JSON error bodies.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class ErrorCode(str, Enum):
    """Machine-readable error codes returned in API error responses."""

    # ── Validation ────────────────────────────────────────────
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"

    # ── Authentication / Authorization ────────────────────────
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"

    # ── Resource ──────────────────────────────────────────────
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"

    # ── Database ──────────────────────────────────────────────
    DATABASE_ERROR = "DATABASE_ERROR"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"

    # ── AI / Groq ─────────────────────────────────────────────
    AI_CONFIGURATION_ERROR = "AI_CONFIGURATION_ERROR"
    AI_AUTHENTICATION_ERROR = "AI_AUTHENTICATION_ERROR"
    AI_RATE_LIMIT_ERROR = "AI_RATE_LIMIT_ERROR"
    AI_TIMEOUT_ERROR = "AI_TIMEOUT_ERROR"
    AI_VALIDATION_ERROR = "AI_VALIDATION_ERROR"
    AI_TOOL_ERROR = "AI_TOOL_ERROR"
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"

    # ── Location ──────────────────────────────────────────────
    LOCATION_PROVIDER_UNAVAILABLE = "LOCATION_PROVIDER_UNAVAILABLE"
    LOCATION_PROVIDER_RATE_LIMITED = "LOCATION_PROVIDER_RATE_LIMITED"
    LOCATION_PROVIDER_INVALID_REQUEST = "LOCATION_PROVIDER_INVALID_REQUEST"

    # ── Rate limiting ─────────────────────────────────────────
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # ── Internal ──────────────────────────────────────────────
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base application error.

    All domain-level exceptions derive from this class so the global
    exception handler in ``main.py`` can catch them uniformly and return
    a JSON body with ``{code, message}`` without leaking tracebacks.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = 500,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}


class ValidationError(AppError):
    def __init__(self, message: str = "Invalid input.", *, detail: Optional[dict[str, Any]] = None):
        super().__init__(ErrorCode.VALIDATION_ERROR, message, status_code=422, detail=detail)


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication required."):
        super().__init__(ErrorCode.AUTHENTICATION_ERROR, message, status_code=401)


class AuthorizationError(AppError):
    def __init__(self, message: str = "Insufficient permissions."):
        super().__init__(ErrorCode.AUTHORIZATION_ERROR, message, status_code=403)


class NotFoundError(AppError):
    def __init__(self, entity: str = "Resource", entity_id: Any = None):
        msg = f"{entity} not found." if entity_id is None else f"{entity} {entity_id} not found."
        super().__init__(ErrorCode.NOT_FOUND, msg, status_code=404)


class AlreadyExistsError(AppError):
    def __init__(self, message: str = "Resource already exists."):
        super().__init__(ErrorCode.ALREADY_EXISTS, message, status_code=409)


class DatabaseError(AppError):
    def __init__(self, message: str = "A database error occurred."):
        super().__init__(ErrorCode.DATABASE_ERROR, message, status_code=503)


class RateLimitError(AppError):
    def __init__(self, message: str = "Too many requests. Please try again shortly."):
        super().__init__(ErrorCode.RATE_LIMIT_EXCEEDED, message, status_code=429)
