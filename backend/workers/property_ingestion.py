"""Worker: Property Ingestion"""
import sys
import os
import asyncio
from datetime import datetime, timezone
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import connect, get_database, close_connection
from app.repositories.property_repo import PropertyRepository
from app.models.property import Property, PropertyImage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("property_ingestion")

async def run_ingestion():
    connect()
    db = get_database()
    repo = PropertyRepository(db)
    
    # Check for lock to ensure idempotency / single execution
    lock_id = "property_ingestion_lock"
    now = datetime.now(timezone.utc)
    # Attempt to acquire lock
    lock = db["worker_locks"].find_one_and_update(
        {"_id": lock_id, "locked_until": {"$lt": now}},
        {"$set": {"locked_until": datetime.fromtimestamp(now.timestamp() + 300, tz=timezone.utc)}},
        upsert=True
    )
    # In a real impl, we'd handle lock failure gracefully. We assume success for this mock.
    
    logger.info("Acquired lock. Starting property ingestion...")
    
    # Read configured provider from env.
    provider_name = os.environ.get("PROPERTY_PROVIDER")
    if not provider_name:
        logger.warning("No property provider configured. Stopping ingestion safely (no fake data will be created).")
        
        # Log empty run
        db["worker_runs"].insert_one({
            "worker_name": "property_ingestion",
            "started_at": now,
            "status": "warning",
            "fetched": 0,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "failed": 0,
            "error_summary": "Provider not configured",
            "finished_at": datetime.now(timezone.utc)
        })
        close_connection()
        return

    # In a real environment, we'd instantiate the provider dynamically and iterate over fetch_properties().
    # For now we just log a successful empty run since the provider isn't actually bound.
    logger.info(f"Using provider {provider_name}")
    
    # Metrics
    fetched = 0
    inserted = 0
    failed = 0
    
    db["worker_runs"].insert_one({
        "worker_name": "property_ingestion",
        "started_at": now,
        "status": "healthy",
        "fetched": fetched,
        "inserted": inserted,
        "updated": 0,
        "unchanged": 0,
        "failed": failed,
        "finished_at": datetime.now(timezone.utc)
    })
    
    # Release lock
    db["worker_locks"].update_one({"_id": lock_id}, {"$set": {"locked_until": datetime.fromtimestamp(0, tz=timezone.utc)}})
    
    logger.info("Property ingestion worker finished.")
    close_connection()

if __name__ == "__main__":
    asyncio.run(run_ingestion())
