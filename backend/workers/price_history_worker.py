"""Worker: Price History Normalization (CLI entry point).

Validates price_history records and computes per-property price summaries.
Idempotent; never fabricates history.
"""
import sys
import os
import asyncio
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import connect, get_database, close_connection
from app.workers.price_history import run_price_history_normalizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("price_history_worker")


async def main() -> None:
    connect()
    db = get_database()
    try:
        result = await asyncio.to_thread(run_price_history_normalizer, db)
        logger.info("price_history_worker result=%s", result)
    finally:
        close_connection()


if __name__ == "__main__":
    asyncio.run(main())
