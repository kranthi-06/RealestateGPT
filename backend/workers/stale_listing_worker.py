"""Worker: Stale Listing Detection"""
import sys
import os
import asyncio
from datetime import datetime, timezone, timedelta
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import connect, get_database, close_connection
from app.repositories.property_repo import PropertyRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("stale_listing_worker")

async def run_stale_detection():
    connect()
    db = get_database()
    repo = PropertyRepository(db)
    
    lock_id = "stale_listing_lock"
    now = datetime.now(timezone.utc)
    
    try:
        db["worker_locks"].update_one(
            {"_id": lock_id, "locked_until": {"$lt": now}},
            {"$set": {"locked_until": datetime.fromtimestamp(now.timestamp() + 300, tz=timezone.utc)}},
            upsert=True
        )
    except Exception:
        logger.info("Could not acquire lock. Exiting.")
        close_connection()
        return

    logger.info("Starting stale listing detection...")
    
    # Example threshold: 7 days
    stale_threshold = now - timedelta(days=7)
    
    # Find properties that are still "active" but haven't been seen in a week.
    stale_cursor = db["properties"].find({
        "status": "active",
        "last_seen_at": {"$lt": stale_threshold}
    })
    
    stale_count = 0
    updated_count = 0
    failed_count = 0
    
    for prop in stale_cursor:
        stale_count += 1
        try:
            # We don't automatically mark as sold unless we know. 
            # We mark as inactive/unknown
            db["properties"].update_one(
                {"_id": prop["_id"]},
                {"$set": {
                    "status": "inactive",
                    "updated_at": now
                }}
            )
            updated_count += 1
        except Exception as e:
            logger.error(f"Failed to update stale property {prop['_id']}: {e}")
            failed_count += 1

    db["worker_runs"].insert_one({
        "worker_name": "stale_listing_worker",
        "started_at": now,
        "status": "healthy",
        "stale": stale_count,
        "updated": updated_count,
        "failed": failed_count,
        "finished_at": datetime.now(timezone.utc)
    })
    
    db["worker_locks"].update_one({"_id": lock_id}, {"$set": {"locked_until": datetime.fromtimestamp(0, tz=timezone.utc)}})
    
    logger.info(f"Stale listing worker finished. {updated_count} listings marked inactive.")
    close_connection()

if __name__ == "__main__":
    asyncio.run(run_stale_detection())
