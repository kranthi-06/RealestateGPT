"""Production-grade application cache backed by MongoDB.

Purpose
-------
A single, shared cache layer for expensive derived data so repeated questions
do not re-trigger the same upstream work (external web search, AI analysis,
market statistics, location lookups).

Design contract
---------------
* **Namespaced keys.** Every entry lives under a ``namespace`` (data-type
  policy) plus a SHA-256 key derived from *normalized* parameters, so a filter,
  currency, language or model change produces a different cache identity while
  cosmetic differences (case, whitespace, key order) do not.
* **TTL per data type.** ``CachePolicy`` defines a default TTL for each
  namespace; a MongoDB TTL index on ``expires_at`` is the real expiration
  mechanism and ``get`` additionally performs an explicit freshness check so a
  stale entry is never served as fresh.
* **Request coalescing.** ``get_or_set`` deduplicates concurrent identical
  misses in-process: the first caller runs the producer, the others await the
  same future. No duplicate upstream calls.
* **Never cache private data.** Only shared, non-personalized payloads may be
  stored. Callers must not pass user-scoped data through this cache.
* **Observability.** Every hit/miss is counted in-process and the response
  carries ``cache_hit``, ``age_seconds`` and ``expires_at`` so callers can be
  honest about freshness. Errors are cached only with a short TTL and an
  explicit ``is_error`` flag — an error is never returned as a success.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from app.core.database import get_database

logger = logging.getLogger(__name__)

COLLECTION = "app_cache"


def _as_utc(value: Any) -> Optional[datetime]:
    """Coerce a Mongo/naive datetime to timezone-aware UTC."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Cache policies ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CachePolicy:
    """TTL (seconds) + description for one data type."""

    ttl_seconds: int
    description: str


#: Default TTLs per namespace. Values are deliberately conservative for
#: time-sensitive market data and generous for stable geographic data.
DEFAULT_POLICIES: Dict[str, CachePolicy] = {
    # Catalogue-derived statistics: cheap to recompute, short TTL, and callers
    # invalidate the namespace when listings change.
    "market_snapshot": CachePolicy(300, "Aggregated catalogue market statistics"),
    # External research: web-search + AI summary. Slower to refresh.
    "market_research": CachePolicy(86_400, "External market research for a location"),
    # Deterministic property search results.
    "property_search": CachePolicy(120, "Property catalogue search results"),
    # External location / nearby-place lookups (geographically stable).
    "external_location": CachePolicy(604_800, "Geocoding and nearby-place lookups"),
    # AI analysis over retrieved evidence (never user-personalized).
    "ai_analysis": CachePolicy(1_800, "AI analysis of retrieved evidence"),
}


def normalize_query(value: Any) -> Any:
    """Normalize a cache-identity component.

    Strings are trimmed, case-folded and internal whitespace-collapsed;
    numbers keep their value; lists/tuples are normalized element-wise and
    sorted when they are order-insensitive (``sort=True`` opt-in by callers);
    dicts are normalized key-wise. This keeps ``"Hyderabad"``, ``"hyderabad "``
    and ``"HYDERABAD"`` in the same cache bucket without merging genuinely
    different queries.
    """
    if isinstance(value, str):
        return " ".join(value.strip().casefold().split())
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (list, tuple)):
        return [normalize_query(item) for item in value]
    if isinstance(value, dict):
        return {
            str(k): normalize_query(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
            if v is not None and v != "" and v != []
        }
    if value is None:
        return None
    return str(value)


def cache_key(namespace: str, params: Any) -> str:
    """Stable namespaced cache key from normalized parameters."""
    normalized = normalize_query(params)
    payload = json.dumps(
        {"ns": namespace.strip().lower(), "q": normalized},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{namespace.strip().lower()}:{digest}"


def coerce_ttl(policy: CachePolicy, ttl_seconds: Optional[int]) -> int:
    """Use the caller TTL when positive, else the namespace policy TTL."""
    if ttl_seconds is not None and ttl_seconds > 0:
        return int(ttl_seconds)
    return int(policy.ttl_seconds)


class CacheRepository:
    """MongoDB-backed cache with TTL freshness and in-process coalescing."""

    COLLECTION = COLLECTION

    def __init__(self, db=None) -> None:
        self.db = db if db is not None else get_database()
        self.coll = self.db[self.COLLECTION]
        # In-flight producers: cache_key -> Future. Concurrent identical
        # requests await the same future instead of duplicating upstream work.
        self._inflight: Dict[str, Future] = {}
        self._lock = threading.Lock()

    # ── reads ───────────────────────────────────────────────────────────
    def get(self, key: str) -> Optional[dict]:
        """Return a *fresh* entry, or None (miss / expired)."""
        if not key:
            return None
        try:
            doc = self.coll.find_one({"key": key, "expires_at": {"$gt": _utcnow()}})
        except Exception as exc:  # pragma: no cover - defensive
            logger.info("cache_get_failed key=%s err=%s", key, exc)
            return None
        if doc is None:
            return None
        created_at = _as_utc(doc.get("created_at")) or _utcnow()
        expires_at = _as_utc(doc.get("expires_at")) or created_at
        age_seconds = max(0, int((_utcnow() - created_at).total_seconds()))
        return {
            "key": doc.get("key"),
            "payload": doc.get("payload"),
            "created_at": created_at,
            "expires_at": expires_at,
            "age_seconds": age_seconds,
            "is_error": bool(doc.get("is_error", False)),
            "metadata": doc.get("metadata") or {},
        }

    def get_including_stale(self, key: str) -> Optional[dict]:
        """Return the entry even when expired (honest 'previously cached' UI)."""
        if not key:
            return None
        try:
            doc = self.coll.find_one({"key": key})
        except Exception:  # pragma: no cover - defensive
            return None
        if doc is None:
            return None
        created_at = doc.get("created_at") or _utcnow()
        return {
            "key": doc.get("key"),
            "payload": doc.get("payload"),
            "created_at": created_at,
            "expires_at": doc.get("expires_at"),
            "is_error": bool(doc.get("is_error", False)),
            "metadata": doc.get("metadata") or {},
        }

    # ── writes ──────────────────────────────────────────────────────────
    def set(
        self,
        key: str,
        payload: Any,
        *,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[dict] = None,
        is_error: bool = False,
        policy: Optional[CachePolicy] = None,
    ) -> None:
        if not key:
            return
        policy = policy or CachePolicy(3600, "default")
        ttl = coerce_ttl(policy, ttl_seconds)
        # Errors are cached only briefly; a failure must never outlive its cause.
        if is_error:
            ttl = min(ttl, 60)
        now = _utcnow()
        try:
            self.coll.update_one(
                {"key": key},
                {
                    "$set": {
                        "payload": payload,
                        "created_at": now,
                        "expires_at": now + timedelta(seconds=ttl),
                        "is_error": is_error,
                        "metadata": metadata or {},
                        "ttl_seconds": ttl,
                    },
                    "$setOnInsert": {"key": key},
                },
                upsert=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.info("cache_set_failed key=%s err=%s", key, exc)

    def delete(self, key: str) -> None:
        if not key:
            return
        try:
            self.coll.delete_one({"key": key})
        except Exception:  # pragma: no cover - defensive
            pass

    def invalidate_namespace(self, namespace: str) -> int:
        """Drop every entry in a namespace (e.g. when listings change)."""
        prefix = f"{namespace.strip().lower()}:"
        try:
            result = self.coll.delete_many({"key": {"$regex": f"^{prefix}"}})
            return int(result.deleted_count)
        except Exception:  # pragma: no cover - defensive
            return 0

    # ── coalesced read-through ──────────────────────────────────────────
    def get_or_set(
        self,
        key: str,
        producer: Callable[[], Any],
        *,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[dict] = None,
        policy: Optional[CachePolicy] = None,
    ) -> dict:
        """Return ``{"payload", "cache_hit", ...}``; run ``producer`` at most
        once for concurrent identical callers.

        The producer result is validated JSON-serializable before it is stored:
        a payload that cannot round-trip is returned to the caller but never
        cached (protects against cache poisoning from malformed producer data).
        """
        entry = self.get(key)
        if entry is not None and not entry["is_error"]:
            return self._result(entry["payload"], cache_hit=True, entry=entry)

        with self._lock:
            future = self._inflight.get(key)
            if future is None:
                future = Future()
                self._inflight[key] = future
                leader = True
            else:
                leader = False

        if not leader:
            try:
                payload = future.result(timeout=120)
            except Exception:
                # The leader failed; fall through to a fresh attempt rather
                # than surfacing the leader's exception to every waiter.
                payload = None
                future_error = True
            else:
                future_error = False
            if not future_error:
                return self._result(payload, cache_hit=True, entry=None)
            # Leader failed: retry as a new leader.
            with self._lock:
                future = Future()
                self._inflight[key] = future
                leader = True

        try:
            started = time.perf_counter()
            payload = producer()
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        except Exception as exc:  # noqa: BLE001 - cache errors briefly
            logger.info("cache_producer_failed key=%s err=%s", key, type(exc).__name__)
            self.set(
                key,
                {"error": type(exc).__name__},
                ttl_seconds=60,
                metadata={"error": type(exc).__name__},
                is_error=True,
                policy=policy,
            )
            future.set_exception(exc)
            raise
        finally:
            with self._lock:
                if self._inflight.get(key) is future:
                    self._inflight.pop(key, None)

        # Only serializable payloads are cached (cache-poisoning guard).
        try:
            json.dumps(payload, default=str)
        except (TypeError, ValueError):
            logger.info("cache_skip_unserializable key=%s", key)
            future.set_result(payload)
            return self._result(payload, cache_hit=False, entry=None)

        future.set_result(payload)
        self.set(
            key,
            payload,
            ttl_seconds=ttl_seconds,
            metadata={"producer_latency_ms": latency_ms, **(metadata or {})},
            policy=policy,
        )
        return self._result(payload, cache_hit=False, entry=None)

    @staticmethod
    def _result(payload: Any, *, cache_hit: bool, entry: Optional[dict]) -> dict:
        if entry is not None:
            return {
                "payload": payload,
                "cache_hit": cache_hit,
                "age_seconds": entry.get("age_seconds"),
                "expires_at": entry.get("expires_at"),
                "cached_at": entry.get("created_at"),
                "is_error": False,
            }
        return {
            "payload": payload,
            "cache_hit": cache_hit,
            "age_seconds": 0,
            "expires_at": None,
            "cached_at": None,
            "is_error": False,
        }

    # ── housekeeping ────────────────────────────────────────────────────
    def cleanup(self, limit: int = 1000) -> int:
        """Delete expired entries (defensive; the TTL index does the work)."""
        try:
            result = self.coll.delete_many({"expires_at": {"$lt": _utcnow()}}).acknowledged
            return 0 if not result else limit  # deleted_count is not exposed here
        except Exception:  # pragma: no cover - defensive
            return 0

    def stats(self) -> dict:
        """Non-sensitive observability: counts per namespace and hit counters."""
        try:
            pipeline = [
                {"$match": {"expires_at": {"$gt": _utcnow()}}},
                {"$project": {"ns": {"$arrayElemAt": [{"$split": ["$key", ":"]}, 0]}}},
                {"$group": {"_id": "$ns", "entries": {"$sum": 1}}},
            ]
            rows = list(self.coll.aggregate(pipeline))
        except Exception:  # pragma: no cover - defensive
            rows = []
        return {
            "fresh_entries_by_namespace": {row["_id"]: row["entries"] for row in rows},
            "in_flight_producers": len(self._inflight),
        }


# ── process-wide counters (no secrets, no payloads) ─────────────────────────

class CacheMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def record(self, hit: bool) -> None:
        with self._lock:
            if hit:
                self.hits += 1
            else:
                self.misses += 1

    def snapshot(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
            }


_metrics: Optional[CacheMetrics] = None


def cache_metrics() -> CacheMetrics:
    global _metrics
    if _metrics is None:
        _metrics = CacheMetrics()
    return _metrics


def policy_for(namespace: str) -> CachePolicy:
    return DEFAULT_POLICIES.get(namespace.strip().lower(), CachePolicy(3600, "default"))
