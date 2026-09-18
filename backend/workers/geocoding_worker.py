"""Worker: Geocoding"""
import sys
import os
import time
from datetime import datetime, timezone
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pymongo.errors import DuplicateKeyError
from app.core.database import connect, get_database, close_connection
from app.providers.location import get_location_provider, LocationProviderUnavailable

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("geocoding_worker")

def run_geocoding():
    connect()
    db = get_database()
    
    lock_id = "geocoding_worker_lock"
    now = datetime.now(timezone.utc)
    
    # 4. Prevent concurrent geocoding workers from exceeding the provider limit.
    try:
        db["worker_locks"].insert_one({
            "_id": lock_id,
            "locked_until": datetime.fromtimestamp(now.timestamp() + 300, tz=timezone.utc)
        })
    except DuplicateKeyError:
        res = db["worker_locks"].update_one(
            {"_id": lock_id, "locked_until": {"$lt": now}},
            {"$set": {"locked_until": datetime.fromtimestamp(now.timestamp() + 300, tz=timezone.utc)}}
        )
        if res.modified_count == 0:
            logger.info("Worker is already locked by another process.")
            close_connection()
            return

    logger.info("Starting geocoding worker...")
    
    # 7. Make the provider replaceable.
    provider = get_location_provider()
    
    # 1. Process only properties actually missing coordinates.
    # 9. Do not block the entire ingestion pipeline (limit batch size).
    cursor = db["properties"].find({
        "status": "active",
        "$or": [
            {"latitude": None},
            {"longitude": None}
        ]
    }).limit(20)
    
    fetched = 0
    updated = 0
    failed = 0
    
    for prop in cursor:
        fetched += 1
        address = prop.get("address") or f"{prop.get('locality', '')}, {prop.get('city', '')}"
        address = address.strip().strip(',')
        if not address:
            failed += 1
            continue

        # 2. Cache every successful geocoding result.
        # 5. Do not repeatedly geocode the same address.
        cached = db["geocode_cache"].find_one({"address": address})
        if cached:
            if cached.get("latitude") is not None and cached.get("longitude") is not None:
                db["properties"].update_one(
                    {"_id": prop["_id"]},
                    {"$set": {
                        "latitude": cached["latitude"],
                        "longitude": cached["longitude"],
                        "location": {"type": "Point", "coordinates": [cached["longitude"], cached["latitude"]]},
                        "updated_at": datetime.now(timezone.utc)
                    }}
                )
                updated += 1
            else:
                failed += 1
            continue
            
        try:
            # 6. Keep geocoding behind LocationProvider.
            result = provider.geocode(address)
            lat = result.get("latitude")
            lon = result.get("longitude")
            
            db["geocode_cache"].insert_one({
                "address": address,
                "latitude": lat,
                "longitude": lon,
                "provider": provider.name,
                "created_at": datetime.now(timezone.utc)
            })
            
            db["properties"].update_one(
                {"_id": prop["_id"]},
                {"$set": {
                    "latitude": lat,
                    "longitude": lon,
                    "location": {"type": "Point", "coordinates": [lon, lat]},
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            updated += 1
            
        except LocationProviderUnavailable as e:
            # 8. Log provider/rate-limit failures.
            logger.error(f"Geocoding provider unavailable for '{address}': {e}")
            failed += 1
            db["geocode_cache"].insert_one({
                "address": address,
                "latitude": None,
                "longitude": None,
                "error": str(e),
                "created_at": datetime.now(timezone.utc)
            })
        except Exception as e:
            logger.error(f"Geocoding failed for property {prop['_id']} ('{address}'): {e}")
            failed += 1
            db["geocode_cache"].insert_one({
                "address": address,
                "latitude": None,
                "longitude": None,
                "error": str(e),
                "created_at": datetime.now(timezone.utc)
            })
            
        # 3. Enforce strict rate limiting.
        time.sleep(1.5)

    db["worker_runs"].insert_one({
        "worker_name": "geocoding_worker",
        "started_at": now,
        "status": "healthy",
        "fetched": fetched,
        "updated": updated,
        "failed": failed,
        "finished_at": datetime.now(timezone.utc)
    })
    
    db["worker_locks"].update_one({"_id": lock_id}, {"$set": {"locked_until": datetime.fromtimestamp(0, tz=timezone.utc)}})
    logger.info(f"Geocoding worker finished. Fetched {fetched}, Updated {updated}, Failed {failed}.")
    close_connection()

if __name__ == "__main__":
    run_geocoding()
