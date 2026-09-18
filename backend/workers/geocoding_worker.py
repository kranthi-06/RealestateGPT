"""Worker: Geocoding (CLI entry point).

Resolves properties missing coordinates through the configured location
provider. Cache + failure TTL + rate limiting + single-flight lock preserved.
"""
import sys
import os
import asyncio
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import connect, get_database, close_connection
from app.workers.geocoding import run_geocoding

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("geocoding_worker")


async def main() -> None:
    connect()
    db = get_database()
    try:
        result = await asyncio.to_thread(run_geocoding, db)
        logger.info("geocoding_worker result=%s", result)
    finally:
        close_connection()


if __name__ == "__main__":
    asyncio.run(main())
