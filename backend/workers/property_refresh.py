"""Worker: Property Refresh (CLI entry point).

Re-verifies active listings with the configured provider. Provider failures
never mark a listing unavailable; only provider-confirmed states are terminal.
"""
import sys
import os
import asyncio
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import connect, get_database, close_connection
from app.workers.refresh import run_property_refresh

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("property_refresh")


async def main() -> None:
    connect()
    db = get_database()
    try:
        result = await asyncio.to_thread(run_property_refresh, db)
        logger.info("property_refresh result=%s", result)
    finally:
        close_connection()


if __name__ == "__main__":
    asyncio.run(main())
