"""Schema v2 migration: canonical property fields without breaking existing data.

Backfills:
  * source_listing_id   <- source_id (keeping both in sync)
  * transaction_type    <- listing_type
  * postal_code         <- pincode
  * maintenance          <- maintenance_charge
  * images[] objects     <- legacy comma-joined image_urls string
  * first_seen_at       <- created_at when missing (historical best-effort)
  * status default        <- "unknown" stays untouched (never fabricates availability)
  * rent_amount          <- price for rent listings when missing
  * location_source       set when latitude/longitude already present

Price history normalization:
  * change_type/changed_at backfilled when missing (never invents changes)

Idempotent: tracked in ``schema_migrations`` and each individual rule is a
no-op when its precondition already holds.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MIGRATION_NAME = "schema_v2_property_canonical"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _already_applied(db) -> bool:
    return db["schema_migrations"].find_one({"_id": MIGRATION_NAME}) is not None


def _mark_applied(db) -> None:
    db["schema_migrations"].update_one(
        {"_id": MIGRATION_NAME},
        {"$set": {"applied_at": _utcnow(), "applied": True}},
        upsert=True,
    )


def _migrate_property(db, doc: dict) -> None:
    updates: dict = {}
    pid = doc["_id"]

    if not doc.get("source_listing_id") and doc.get("source_id"):
        updates["source_listing_id"] = doc["source_id"]
    if not doc.get("transaction_type") and doc.get("listing_type"):
        updates["transaction_type"] = doc["listing_type"]
    if not doc.get("postal_code")and doc.get("pincode"):
        updates["postal_code"] = doc["pincode"]
    if doc.get("maintenance") is None and doc.get("maintenance_charge") is not None:
        updates["maintenance"] = doc["maintenance_charge"]
    if not doc.get("images")and doc.get("image_urls"):
        urls = [u.strip() for u in str(doc["image_urls"]).split(",") if u.strip()]
        if urls:
            updates["images"] = [
                {"url": url, "display_order": index, "rights_status": "unknown"}
                for index, url in enumerate(urls)
            ]
    if not doc.get("first_seen_at")and doc.get("created_at"):
        updates["first_seen_at"] = doc["created_at"]
    if not doc.get("listed_at")and doc.get("created_at"):
        updates["listed_at"] = doc["created_at"]
    if not doc.get("rent_amount")and doc.get("listing_type") == "rent"and doc.get("price"):
        updates["rent_amount"] = doc["price"]
    if not doc.get("location_source") and doc.get("latitude") is not None and doc.get("longitude") is not None:
        updates["location_source"] = "legacy"

    if updates:
        updates["updated_at"] = _utcnow()
        db["properties"].update_one({"_id": pid}, {"$set": updates})


def _migrate_price_history(db) -> None:
    for doc in db["price_history"].find({}):
        updates: dict = {}
        if not doc.get("changed_at"):
            updates["changed_at"] = doc.get("created_at") or _utcnow()
        if not doc.get("change_type"):
            old = doc.get("old_price")
            new = doc.get("new_price")
            if old is not None and new is not None and float(old) != float(new):
                updates["change_type"] = "price_increased" if float(new) > float(old) else "price_decreased"
            else:
                updates["change_type"] = "initial_listing"
        if updates:
            db["price_history"].update_one({"_id": doc["_id"]}, {"$set": updates})


_COUNTER_COLLECTIONS = [
    "properties", "users", "audit_logs", "conversations", "messages",
    "documents", "document_chunks", "notifications", "saved_properties",
    "saved_searches", "comparisons", "search_history", "recommendations",
    "dedup_reviews", "worker_runs", "geocode_queue",
]


def repair_counters(db) -> None:
    """Never let integer-id counters drift below the highest existing row.

    Idempotent and always run: if a counter was reset (restore, manual cleanup,
    crash) the next startup repairs it so inserts cannot collide with the
    highest existing ``_id``. Cheap at boot scale via a single max() scan.
    """
    for name in _COUNTER_COLLECTIONS:
        collection = db[name]
        max_doc = collection.find_one(sort=[("_id", -1)])
        if max_doc is None:
            continue
        max_id = max_doc.get("_id")
        if not isinstance(max_id, int):
            continue
        # Ensure the counter row exists, then bump it only when it is behind.
        db["counters"].update_one({"_id": name}, {"$setOnInsert": {"seq": 0}}, upsert=True)
        result = db["counters"].update_one(
            {"_id": name, "seq": {"$lt": max_id}},
            {"$set": {"seq": max_id}},
        )
        if result.modified_count:
            logger.info("counter_repaired collection=%s seq=%s", name, max_id)


def run_migrations(db) -> None:
    repair_counters(db)
    if _already_applied(db):
        return
    properties = db["properties"].find({})
    migrated = 0
    for doc in properties:
        _migrate_property(db, doc)
        migrated += 1
    _migrate_price_history(db)
    _mark_applied(db)
    logger.info("schema_v2 migration applied; properties scanned=%s", migrated)