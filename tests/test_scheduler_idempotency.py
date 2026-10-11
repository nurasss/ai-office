from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.models import ScheduledJobRun
from services.scheduler import (
    AutonomyScheduler,
    JOB_KEY_AUTONOMOUS_TICK,
    SchedulerPersistenceService,
    _ensure_utc,
)


def configure_scheduler_runtime(monkeypatch, tmp_path) -> datetime:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'scheduler-idempotency.db'}")
    monkeypatch.setenv("AUTONOMY_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_POLL_INTERVAL_SECONDS", "60")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    return datetime(2026, 6, 2, 9, 15, tzinfo=timezone.utc)


def test_duplicate_idempotency_is_skipped(tmp_path, monkeypatch):
    now = configure_scheduler_runtime(monkeypatch, tmp_path)
    scheduler = AutonomyScheduler()

    with get_session() as db:
        persistence = SchedulerPersistenceService(db)
        persistence.ensure_default_jobs(now=now)
        job = persistence.get_job_by_key(JOB_KEY_AUTONOMOUS_TICK)
        assert job is not None
        due_at = now - timedelta(seconds=1)
        job.next_run_at = due_at
        window_key = persistence.build_window_idempotency_key(job=job, scheduled_for=due_at)
        persistence.create_attempt_run(
            job=job,
            idempotency_key=window_key,
            status="success",
            started_at=due_at,
            finished_at=now,
            result_json={"status": "ok", "completed": []},
        )
        db.commit()

    result = asyncio.run(scheduler.tick_once(notify=False, now=now))

    assert len(result) == 1
    assert result[0].status == "skipped"

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
        assert len(runs) == 2
        assert runs[0].status == "success"
        assert runs[1].status == "skipped"
        assert runs[1].result_json is not None
        assert runs[1].result_json["reason"] == "idempotency_conflict"
        assert runs[1].result_json["existing_run_id"] == runs[0].id
