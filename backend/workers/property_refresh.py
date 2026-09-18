"""Worker: Property Refresh"""
import sys
import os
import asyncio
from datetime import datetime, timezone
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import connect, get_database, close_connection
from app.repositories.property_repo import PropertyRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("property_refresh")

async def run_refresh():
    connect()
    db = get_database()
    repo = PropertyRepository(db)
    
    lock_id = "property_refresh_lock"
    now = datetime.now(timezone.utc)
    
    # Try to acquire lock
    try:
        db["worker_locks"].update_one(
            {"_id": lock_id, "locked_until": {"$lt": now}},
            {"$set": {"locked_until": datetime.fromtimestamp(now.timestamp() + 300, tz=timezone.utc)}},
            upsert=True
        )
    except Exception as e:
        logger.info("Could not acquire lock or already locked.")
        close_connection()
        return

    logger.info("Acquired lock. Starting property refresh...")
    
    provider_name = os.environ.get("PROPERTY_PROVIDER")
    if not provider_name:
        logger.warning("No property provider configured. Skipping refresh.")
        db["worker_runs"].insert_one({
            "worker_name": "property_refresh",
            "started_at": now,
            "status": "warning",
            "fetched": 0,
            "updated": 0,
            "unchanged": 0,
            "failed": 0,
            "error_summary": "Provider not configured",
            "finished_at": datetime.now(timezone.utc)
        })
        close_connection()
        return

    fetched = 0
    updated = 0
    unchanged = 0
    failed = 0
    
    # Actual implementation would fetch Active properties and re-verify their status and price
    
    db["worker_runs"].insert_one({
        "worker_name": "property_refresh",
        "started_at": now,
        "status": "healthy",
        "fetched": fetched,
        "updated": updated,
        "unchanged": unchanged,
        "failed": failed,
        "finished_at": datetime.now(timezone.utc)
    })
    
    # Release lock
    db["worker_locks"].update_one({"_id": lock_id}, {"$set": {"locked_until": datetime.fromtimestamp(0, tz=timezone.utc)}})
    
    logger.info("Property refresh worker finished.")
    close_connection()

if __name__ == "__main__":
    asyncio.run(run_refresh())
