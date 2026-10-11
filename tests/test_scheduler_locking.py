from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.models import ScheduledJobRun
from services import autonomy_service
from services.scheduler import (
    AutonomyScheduler,
    JOB_KEY_AUTONOMOUS_TICK,
    SchedulerPersistenceService,
    _ensure_utc,
)


def configure_scheduler_runtime(monkeypatch, tmp_path) -> datetime:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'scheduler-locking.db'}")
    monkeypatch.setenv("AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_POLL_INTERVAL_SECONDS", "60")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    return datetime(2026, 6, 2, 9, 15, tzinfo=timezone.utc)


def test_lock_prevents_concurrent_execution(tmp_path, monkeypatch):
    now = configure_scheduler_runtime(monkeypatch, tmp_path)
    scheduler = AutonomyScheduler()

    with get_session() as db:
        persistence = SchedulerPersistenceService(db)
        persistence.ensure_default_jobs(now=now)
        job = persistence.get_job_by_key(JOB_KEY_AUTONOMOUS_TICK)
        assert job is not None
        job.next_run_at = now - timedelta(seconds=1)
        acquired = persistence.acquire_lock(
            lock_key=job.job_key,
            owner_id="other-scheduler",
            ttl_seconds=300,
            now=now,
        )
        db.commit()

    assert acquired is True

    result = asyncio.run(scheduler.tick_once(notify=False, now=now))

    assert len(result) == 1
    assert result[0].status == "locked"

    with get_session() as db:
        runs = list(
            db.scalars(
                select(ScheduledJobRun)
                .where(ScheduledJobRun.job_key == JOB_KEY_AUTONOMOUS_TICK)
                .order_by(ScheduledJobRun.id.asc())
            )
        )
        assert len(runs) == 1
        assert runs[0].status == "locked"
        assert runs[0].result_json == {
            "reason": "lock_held",
            "scheduled_for": (now - timedelta(seconds=1)).isoformat(),
        }


def test_failed_job_records_failed_status(tmp_path, monkeypatch):
    now = configure_scheduler_runtime(monkeypatch, tmp_path)
    scheduler = AutonomyScheduler()

    async def fail_poll(self, *, notify: bool = True):
        raise RuntimeError("scheduler poll failed")

    monkeypatch.setattr(autonomy_service.AutonomyService, "poll_queued_tasks", fail_poll)

    with get_session() as db:
        persistence = SchedulerPersistenceService(db)
        persistence.ensure_default_jobs(now=now)
        job = persistence.get_job_by_key(JOB_KEY_AUTONOMOUS_TICK)
        assert job is not None
        job.next_run_at = now - timedelta(seconds=1)
        db.commit()

    result = asyncio.run(scheduler.tick_once(notify=False, now=now))

    assert len(result) == 1
    assert result[0].status == "failed"
    assert result[0].error == "scheduler poll failed"

    with get_session() as db:
        persistence = SchedulerPersistenceService(db)
        job = persistence.get_job_by_key(JOB_KEY_AUTONOMOUS_TICK)
        assert job is not None
        assert job.last_run_at is not None
        assert job.next_run_at is not None
        assert _ensure_utc(job.next_run_at) > now

        runs = list(
            db.scalars(
                select(ScheduledJobRun)
                .where(ScheduledJobRun.job_key == JOB_KEY_AUTONOMOUS_TICK)
                .order_by(ScheduledJobRun.id.asc())
            )
        )
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].error == "scheduler poll failed"
