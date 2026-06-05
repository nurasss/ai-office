"""Standalone scheduler process for 24/7 autonomy."""

from __future__ import annotations

import asyncio

from core.db import init_db, should_auto_create_tables
from core.logger import get_logger, setup_logging
from core.production import run_production_preflight
from services.scheduler import autonomy_scheduler

setup_logging("INFO")
logger = get_logger("workers.scheduler")


async def main() -> None:
    run_production_preflight(raise_on_error=True)
    if should_auto_create_tables():
        init_db()
    autonomy_scheduler.start()
    logger.info("scheduler.runner.started")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await autonomy_scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
