"""web_search_cache repository.

Purpose: reduce duplicate provider searches, reduce cost, improve latency.
Cache key is derived from the normalized SearchIntent only — two users asking
the same thing share results, while any filter change produces a different key.
Every entry expires via configurable TTL (WEB_SEARCH_CACHE_TTL_SECONDS) plus a
Mongo TTL index on ``expires_at``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def cache_key_for_intent(intent: dict[str, Any]) -> str:
    """Stable cache key from the normalized SearchIntent dump."""
    import hashlib
    import json

    normalized = json.dumps(intent, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class WebSearchCacheRepository:
    COLLECTION = "web_search_cache"

    def __init__(self, db) -> None:
        self.db = db
        self.coll = db[self.COLLECTION]

    def get(self, cache_key: str) -> Optional[dict[str, Any]]:
        if not cache_key:
            return None
        doc = self.coll.find_one({"cache_key": cache_key, "expires_at": {"$gt": _utcnow()}})
        if doc is None:
            return None
        return {
            "cache_key": doc["cache_key"],
            "query": doc.get("query"),
            "normalized_intent": doc.get("normalized_intent"),
            "results": doc.get("results", []),
            "provider": doc.get("provider"),
            "created_at": doc.get("created_at"),
            "expires_at": doc.get("expires_at"),
        }

    def set(
        self,
        cache_key: str,
        query: str,
        normalized_intent: dict[str, Any],
        results: list[dict[str, Any]],
        provider: str,
        ttl_seconds: int | None = None,
        *,
        stale: bool = False,
    ) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else settings.WEB_SEARCH_CACHE_TTL_SECONDS
        now = _utcnow()
        self.coll.update_one(
            {"cache_key": cache_key},
            {
                "$set": {
                    "query": query,
                    "normalized_intent": normalized_intent,
                    "results": results,
                    "provider": provider,
                    "created_at": now,
                    "expires_at": now + timedelta(seconds=ttl),
                    "stale": stale,
                }
            },
            upsert=True,
        )

    def mark_stale(self, cache_key: str) -> None:
        self.coll.update_one({"cache_key": cache_key}, {"$set": {"stale": True}})

    def get_stale(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Return expired-but-present entries for honest 'previously discovered'
        rendering when the provider fails mid-refresh."""
        doc = self.coll.find_one({"cache_key": cache_key})
        if doc is None:
            return None
        return {
            "cache_key": doc["cache_key"],
            "query": doc.get("query"),
            "results": doc.get("results", []),
            "provider": doc.get("provider"),
            "created_at": doc.get("created_at"),
            "expires_at": doc.get("expires_at"),
            "stale": True,
        }

    def cleanup(self, limit: int = 500) -> int:
        """Delete expired entries (defensive; the TTL index does the real work)."""
        result = self.coll.delete_many({"expires_at": {"$lt": _utcnow()}})
        return int(result.deleted_count)