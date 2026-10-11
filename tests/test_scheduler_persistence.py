from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.models import ScheduledJob, ScheduledJobRun
from services.scheduler import (
    AutonomyScheduler,
    JOB_KEY_AUTONOMOUS_TICK,
    JOB_KEY_DAILY_PLAN,
    JOB_KEY_EVENING_REVIEW,
    SchedulerPersistenceService,
    _ensure_utc,
)


def configure_scheduler_runtime(monkeypatch, tmp_path) -> datetime:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'scheduler.db'}")
    monkeypatch.setenv("AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_POLL_INTERVAL_SECONDS", "60")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    return datetime(2026, 6, 2, 9, 15, tzinfo=timezone.utc)


def test_scheduler_creates_default_jobs(tmp_path, monkeypatch):
    now = configure_scheduler_runtime(monkeypatch, tmp_path)

    with get_session() as db:
        jobs = SchedulerPersistenceService(db).ensure_default_jobs(now=now)
        db.commit()

        assert {job.job_key for job in jobs} == {
            JOB_KEY_DAILY_PLAN,
            JOB_KEY_EVENING_REVIEW,
            JOB_KEY_AUTONOMOUS_TICK,
        }
        persisted = list(db.scalars(select(ScheduledJob).order_by(ScheduledJob.job_key.asc())))
        assert len(persisted) == 3
        assert all(job.next_run_at is not None for job in persisted)


def test_due_job_executes_once_and_updates_next_run_at(tmp_path, monkeypatch):
    now = configure_scheduler_runtime(monkeypatch, tmp_path)
    scheduler = AutonomyScheduler()

    with get_session() as db:
        persistence = SchedulerPersistenceService(db)
        persistence.ensure_default_jobs(now=now)
        job = persistence.get_job_by_key(JOB_KEY_AUTONOMOUS_TICK)
        assert job is not None
        job.next_run_at = now - timedelta(seconds=1)
        db.commit()

    first = asyncio.run(scheduler.tick_once(notify=False, now=now))
    second = asyncio.run(scheduler.tick_once(notify=False, now=now))

    assert [item.status for item in first] == ["success"]
    assert second == []

    with get_session() as db:
        job = SchedulerPersistenceService(db).get_job_by_key(JOB_KEY_AUTONOMOUS_TICK)
        assert job is not None
        assert job.last_run_at is not None
        assert job.next_run_at is not None
        assert _ensure_utc(job.next_run_at) > now

        runs = list(
            db.scalars(
                select(ScheduledJobRun).where(ScheduledJobRun.job_key == JOB_KEY_AUTONOMOUS_TICK)
            )
        )
        assert len(runs) == 1
        assert runs[0].status == "success"


def test_restart_simulation_reads_db_state(tmp_path, monkeypatch):
    now = configure_scheduler_runtime(monkeypatch, tmp_path)
    scheduler1 = AutonomyScheduler()

    with get_session() as db:
        persistence = SchedulerPersistenceService(db)
        persistence.ensure_default_jobs(now=now)
        job = persistence.get_job_by_key(JOB_KEY_AUTONOMOUS_TICK)
        assert job is not None
        job.next_run_at = now - timedelta(seconds=1)
        db.commit()

    asyncio.run(scheduler1.tick_once(notify=False, now=now))

    scheduler2 = AutonomyScheduler()
    with get_session() as db:
        job = SchedulerPersistenceService(db).get_job_by_key(JOB_KEY_AUTONOMOUS_TICK)
        assert job is not None
        assert job.last_run_at is not None
        assert job.next_run_at is not None
        assert _ensure_utc(job.next_run_at) > now

    assert scheduler2.last_poll_run_at is not None
