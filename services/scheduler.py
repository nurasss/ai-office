"""In-process scheduler for the first autonomous runtime MVP."""

from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from core.config import get_settings
from core.db import get_session
from core.logger import get_logger
from services.autonomy_service import AutonomyService, get_autonomy_enabled

logger = get_logger("services.scheduler")


class AutonomyScheduler:
    """Small replaceable scheduler; Celery/RQ can take this role later."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._last_daily_plan_date: str | None = None
        self._last_evening_review_date: str | None = None
        self.last_daily_plan_run_at: str | None = None
        self.last_evening_review_run_at: str | None = None
        self.last_poll_run_at: str | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="ai-office-autonomy")
        logger.info("autonomy.scheduler.started")

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        await self._task
        self._task = None
        logger.info("autonomy.scheduler.stopped")

    async def _run(self) -> None:
        settings = get_settings()
        interval = max(int(settings.autonomy_poll_interval_seconds), 30)
        while not self._stop_event.is_set():
            if get_autonomy_enabled():
                await self._tick()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _tick(self) -> None:
        settings = get_settings()
        tz = ZoneInfo(settings.autonomy_timezone)
        now = datetime.now(tz)
        date_key = now.date().isoformat()

        try:
            with get_session() as db:
                service = AutonomyService(db)
                await service.poll_queued_tasks(notify=True)
                self.last_poll_run_at = now.isoformat(timespec="seconds")
                if (
                    now.hour == settings.autonomy_daily_plan_hour
                    and self._last_daily_plan_date != date_key
                ):
                    await service.daily_plan(notify=True)
                    self._last_daily_plan_date = date_key
                    self.last_daily_plan_run_at = now.isoformat(timespec="seconds")
                if (
                    now.hour == settings.autonomy_evening_review_hour
                    and self._last_evening_review_date != date_key
                ):
                    await service.evening_review(notify=True)
                    self._last_evening_review_date = date_key
                    self.last_evening_review_run_at = now.isoformat(timespec="seconds")
        except Exception as error:
            logger.error("autonomy.scheduler.tick_error", error=str(error), exc_info=True)


autonomy_scheduler = AutonomyScheduler()
