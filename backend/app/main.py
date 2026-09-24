"""RealEstateGPT Backend - FastAPI Application"""

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import close_connection, connect, ensure_indexes, get_database
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.api.v1 import ai, auth, finance, properties, saved, health, admin, locations, search, workers

setup_logging(debug=settings.DEBUG)
logger = logging.getLogger(__name__)


# â”€â”€â”€ Lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _validate_configuration() -> None:
    problems = settings.validate_runtime()
    if problems:
        raise RuntimeError("Invalid environment configuration: " + "; ".join(problems))
    # Optional integrations degrade honestly instead of crashing the process.
    for warning in settings.configuration_warnings():
        logger.warning("configuration_warning %s", warning)


_startup_failure: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: verify configuration, MongoDB connectivity and
    indexes; clean shutdown."""
    # TEMPORARY DIAGNOSTIC (to be reverted): surface the exact startup failure
    # over HTTP so the production traceback is observable without log access.
    global _startup_failure
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.APP_ENV)
    try:
        _validate_configuration()
        # Fail fast when the production database is misconfigured or unreachable.
        connect()
        ensure_indexes()
        # Idempotent schema migrations for legacy records.
        from app.migrations import run_migrations
        run_migrations(get_database())
        logger.info("MongoDB connected, schema indexes ensured")
    except Exception as exc:
        import traceback
        _startup_failure = traceback.format_exc(limit=10)[-4000:]
        logger.error("STARTUP FAILED: %s", exc)
    yield
    close_connection()
    logger.info("Shutting down %s", settings.APP_NAME)


from starlette.types import ASGIApp, Receive, Scope, Send

class StripVercelPrefixMiddleware:
    """Strips the /api/backend prefix passed by Vercel rewrites before routing."""
    def __init__(self, app: ASGIApp):
        self.app = app
        self.prefix = "/api/backend"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and scope["path"].startswith(self.prefix):
            scope["path"] = scope["path"][len(self.prefix):]
            if scope.get("raw_path"):
                prefix_bytes = self.prefix.encode("ascii")
                if scope["raw_path"].startswith(prefix_bytes):
                    scope["raw_path"] = scope["raw_path"][len(prefix_bytes):]
        await self.app(scope, receive, send)

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered real estate decision platform",
    version="1.3.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Fix Vercel routing paths
app.add_middleware(StripVercelPrefixMiddleware)

# CORS middleware
#   ``effective_cors_origins`` = configured origins minus any loopback origin
#   outside development, so a deployed backend never trusts localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.effective_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
# Request-ID + access logging middleware must wrap all routes.
app.add_middleware(RequestContextMiddleware)


# â”€â”€â”€ Security headers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.middleware("http")
async def security_headers(request: Request, call_next):
    # TEMPORARY DIAGNOSTIC (to be reverted): report the captured startup
    # failure instead of an opaque platform 500.
    if _startup_failure is not None:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "STARTUP_FAILED", "detail": _startup_failure},
        )
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    if settings.APP_ENV.strip().lower() == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


# Global exception handler â€” typed AppError first, then generic fallback.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Typed application errors â†’ structured JSON response with code + message.
    from app.core.errors import AppError
    if isinstance(exc, AppError):
        logger.warning(
            "app_error path=%s code=%s message=%s",
            request.url.path, exc.code, exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )
    # Location-provider errors â†’ 503 with provider context.
    from app.providers.location import LocationProviderUnavailable
    if isinstance(exc, LocationProviderUnavailable):
        logger.warning("location_provider_error path=%s error=%s", request.url.path, exc)
        return JSONResponse(
            status_code=503,
            content={"code": "LOCATION_PROVIDER_UNAVAILABLE", "message": str(exc)},
        )
    # Everything else â†’ generic 500 with no internal details leaked.
    logger.error("unhandled_exception path=%s error=%s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"code": "INTERNAL_ERROR", "message": "An internal error occurred. Please try again later."},
    )


# Mount API routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(properties.router, prefix=settings.API_V1_PREFIX)
app.include_router(saved.router, prefix=settings.API_V1_PREFIX)
app.include_router(finance.router, prefix=settings.API_V1_PREFIX)
app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)
app.include_router(ai.router, prefix=settings.API_V1_PREFIX)
app.include_router(locations.router, prefix=settings.API_V1_PREFIX)
app.include_router(search.router, prefix=settings.API_V1_PREFIX)
app.include_router(workers.router, prefix=settings.API_V1_PREFIX)

@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": "1.3.0",
        "docs": "/docs",
        "health": f"{settings.API_V1_PREFIX}/health",
    }