"""Worker: Property Ingestion (CLI entry point).

Runs the full ingestion pipeline against the configured provider. Safe to run
repeatedly — ingestions are idempotent.
"""
import sys
import os
import asyncio
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import connect, get_database, close_connection
from app.workers.ingestion import run_property_ingestion

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("property_ingestion")


async def main() -> None:
    connect()
    db = get_database()
    try:
        result = await asyncio.to_thread(run_property_ingestion, db)
        logger.info("property_ingestion result=%s", result)
    finally:
        close_connection()


if __name__ == "__main__":
    asyncio.run(main())
