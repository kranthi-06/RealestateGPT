"""RealEstateGPT Backend - MongoDB connection, lifecycle, and dependencies.

A single shared PyMongo client with the MongoDB Stable API and connection
pooling is used for the whole process. Collections are only accessed through
repositories; route handlers never talk to Mongo directly.

Startup/shutdown:

    connect()          # fail fast: raises when MONGODB_URI is missing/unreachable
    ensure_indexes()   # idempotent index creation
    get_db()           # FastAPI dependency
    close_connection() # application shutdown
"""
from __future__ import annotations

import logging
from typing import Any

from pymongo import MongoClient
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import PyMongoError
from pymongo.server_api import ServerApi

from app.core.config import settings

logger = logging.getLogger(__name__)

GEO_INDEX = "2dsphere"

_client: MongoClient | None = None
_database: Database | None = None


def _get_client() -> MongoClient:
    """Lazily create the shared client (pymongo connects in the background)."""
    global _client
    if _client is None:
        if not settings.MONGODB_URI:
            raise RuntimeError(
                "MONGODB_URI is not configured. Set it in the environment "
                "before starting the application."
            )
        _client = MongoClient(
            settings.MONGODB_URI,
            server_api=ServerApi("1", strict=False),
            maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
            minPoolSize=1,
            connectTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
            serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
            socketTimeoutMS=settings.MONGODB_SOCKET_TIMEOUT_MS,
            retryWrites=True,
            appname="RealEstateGPT",
        )
    return _client


def get_database() -> Database:
    """Return the configured application database (lazy)."""
    global _database
    if _database is None:
        _database = _get_client()[settings.MONGODB_DATABASE]
    return _database


def get_db():
    """FastAPI dependency: yields the database handle for repository layers."""
    return get_database()


def ping() -> bool:
    """Cheap connectivity check against the MongoDB server."""
    try:
        return _get_client().admin.command("ping").get("ok") == 1.0
    except PyMongoError as exc:  # pragma: no cover - network path
        logger.warning("MongoDB ping failed: %s", exc)
        return False


def connect() -> None:
    """Verify configuration and connectivity at startup. Fail loud, never fall back."""
    if not settings.MONGODB_URI:
        raise RuntimeError("MONGODB_URI is not configured.")
    if not ping():
        raise RuntimeError("MongoDB is unreachable with the configured MONGODB_URI.")


def close_connection() -> None:
    """Close pooled connections (application shutdown)."""
    global _client, _database
    if _client is not None:
        _client.close()
    _client = None
    _database = None


def next_id(db: Database, collection: str) -> int:
    """Atomically allocate a monotonically increasing integer document id.

    Integer ids preserve the pre-migration API contract (``int`` fields in the
    Pydantic schemas and TypeScript types) while keeping document ``_id`` the
    same value used for routing. Never call this outside repositories.
    """
    counter = db["counters"].find_one_and_update(
        {"_id": collection},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(counter["seq"])


def ensure_indexes() -> None:
    """Create all production indexes (idempotent; run once at startup)."""
    db = get_database()

    db["users"].create_index("email", unique=True)
    db["users"].create_index("created_at")

    properties = db["properties"]
    properties.create_index([("location", GEO_INDEX)])
    properties.create_index("city")
    properties.create_index("locality")
    properties.create_index([("price", 1)])
    properties.create_index("property_type")
    properties.create_index("bedrooms")
    properties.create_index("created_at")
    properties.create_index("updated_at")
    properties.create_index("is_active")
    properties.create_index("status")
    properties.create_index("last_seen_at")
    properties.create_index("last_verified_at")
    properties.create_index("verification_status")
    properties.create_index("listing_type")
    properties.create_index("amenities.name")
    properties.create_index("source")
    properties.create_index("source_id")
    properties.create_index(
        [("source", 1), ("source_id", 1)], unique=True,
        partialFilterExpression={"source_id": {"$exists": True}}, name="source_source_id_unique",
    )
    properties.create_index(
        [("city", 1), ("property_type", 1), ("bedrooms", 1), ("price", 1)]
    )
    
    db["price_history"].create_index([("property_id", 1), ("changed_at", -1)])

    db["saved_properties"].create_index(
        [("user_id", 1), ("property_id", 1)], unique=True
    )
    db["saved_searches"].create_index("user_id")
    db["comparisons"].create_index("user_id")
    db["conversations"].create_index("user_id")
    db["messages"].create_index("conversation_id")
    db["documents"].create_index("user_id")
    db["audit_logs"].create_index("created_at")
    db["notifications"].create_index([("user_id", 1), ("created_at", -1)])
    db["nearby_places"].create_index([("location", GEO_INDEX)])
    db["nearby_places"].create_index("city")
    logger.info("MongoDB indexes ensured for database %s", settings.MONGODB_DATABASE)


def point(latitude: float, longitude: float) -> dict[str, Any]:
    """GeoJSON Point: coordinates are [longitude, latitude] per the GeoJSON spec."""
    return {"type": "Point", "coordinates": [longitude, latitude]}
