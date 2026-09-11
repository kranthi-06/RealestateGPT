"""RealEstateGPT Backend - FastAPI Application"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import close_connection, connect, ensure_indexes
from app.api.v1 import ai, auth, properties, saved, health, admin, locations

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: verify MongoDB connectivity and indexes; clean shutdown."""
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.APP_ENV)
    # Fail fast when the production database is misconfigured or unreachable.
    connect()
    ensure_indexes()
    logger.info("MongoDB connected, schema indexes ensured")
    yield
    close_connection()
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered real estate decision platform",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Please try again later."},
    )


# Mount API routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(properties.router, prefix=settings.API_V1_PREFIX)
app.include_router(saved.router, prefix=settings.API_V1_PREFIX)
app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)
app.include_router(ai.router, prefix=settings.API_V1_PREFIX)
app.include_router(locations.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": "1.1.0",
        "docs": "/docs",
        "health": f"{settings.API_V1_PREFIX}/health",
    }