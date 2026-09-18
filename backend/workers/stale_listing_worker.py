"""Worker: Stale Listing Detection (CLI entry point).

Active -> stale -> expired lifecycle driven by provider absence windows.
"""
import sys
import os
import asyncio
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import connect, get_database, close_connection
from app.workers.stale import run_stale_detection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("stale_listing_worker")


async def main() -> None:
    connect()
    db = get_database()
    try:
        result = await asyncio.to_thread(run_stale_detection, db)
        logger.info("stale_listing_worker result=%s", result)
    finally:
        close_connection()


if __name__ == "__main__":
    asyncio.run(main())
