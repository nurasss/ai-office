"""DB-backed scheduler for autonomous runtime jobs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.config import get_settings
from core.db import get_session
from core.logger import get_logger
from core.models import ScheduledJob, ScheduledJobRun, SchedulerLock, utc_now
from services.audit_service import audit_log
from services.autonomy_service import AutonomyService, get_autonomy_enabled

logger = get_logger("services.scheduler")

JOB_KEY_DAILY_PLAN = "daily_plan"
JOB_KEY_EVENING_REVIEW = "evening_review"
JOB_KEY_AUTONOMOUS_TICK = "autonomous_tick"


@dataclass(slots=True)
class JobExecutionResult:
    job_key: str
    status: str
    idempotency_key: str
    run_id: int | None = None
    result_json: dict[str, object] | None = None
    error: str | None = None


class SchedulerPersistenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_default_jobs(self, *, now: datetime | None = None) -> list[ScheduledJob]:
        current = _ensure_utc(now or utc_now())
        settings = get_settings()
        definitions = [
            {
                "job_key": JOB_KEY_DAILY_PLAN,
                "schedule_type": "daily",
                "cron_expr": None,
                "interval_seconds": None,
                "timezone": settings.autonomy_timezone,
                "payload_json": {"hour": settings.autonomy_daily_plan_hour, "minute": 0},
            },
            {
                "job_key": JOB_KEY_EVENING_REVIEW,
                "schedule_type": "daily",
                "cron_expr": None,
                "interval_seconds": None,
                "timezone": settings.autonomy_timezone,
                "payload_json": {"hour": settings.autonomy_evening_review_hour, "minute": 0},
            },
            {
                "job_key": JOB_KEY_AUTONOMOUS_TICK,
                "schedule_type": "interval",
                "cron_expr": None,
                "interval_seconds": max(int(settings.autonomy_poll_interval_seconds), 30),
                "timezone": "UTC",
                "payload_json": {"notify": True},
            },
        ]

        existing = {
            job.job_key: job
            for job in self.db.scalars(select(ScheduledJob))
        }
        jobs: list[ScheduledJob] = []
        for definition in definitions:
            job = existing.get(definition["job_key"])
            if job is None:
                job = ScheduledJob(
                    job_key=definition["job_key"],
                    enabled=True,
                    schedule_type=str(definition["schedule_type"]),
                    cron_expr=definition["cron_expr"],
                    interval_seconds=definition["interval_seconds"],
                    timezone=str(definition["timezone"]),
                    payload_json=dict(definition["payload_json"] or {}),
                    next_run_at=current,
                )
                job.next_run_at = self.compute_next_run_at(job, reference=current, initial=True)
                self.db.add(job)
            else:
                job.schedule_type = str(definition["schedule_type"])
                job.cron_expr = definition["cron_expr"]
                job.interval_seconds = definition["interval_seconds"]
                job.timezone = str(definition["timezone"])
                job.payload_json = dict(definition["payload_json"] or {})
                if job.next_run_at is None:
                    job.next_run_at = self.compute_next_run_at(job, reference=current, initial=True)
            jobs.append(job)
        self.db.flush()
        return jobs

    def due_jobs(self, *, now: datetime | None = None) -> list[ScheduledJob]:
        current = _ensure_utc(now or utc_now())
        return list(
            self.db.scalars(
                select(ScheduledJob)
                .where(ScheduledJob.enabled.is_(True))
                .where(ScheduledJob.next_run_at.is_not(None))
                .where(ScheduledJob.next_run_at <= current)
                .order_by(ScheduledJob.next_run_at.asc(), ScheduledJob.id.asc())
            )
        )

    def get_job_by_key(self, job_key: str) -> ScheduledJob | None:
        return self.db.scalar(select(ScheduledJob).where(ScheduledJob.job_key == job_key))

    def acquire_lock(
        self,
        *,
        lock_key: str,
        owner_id: str,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        current = _ensure_utc(now or utc_now())
        self.db.execute(
            delete(SchedulerLock).where(
                SchedulerLock.lock_key == lock_key,
                SchedulerLock.expires_at <= current,
            )
        )
        self.db.flush()
        lock = self.db.scalar(select(SchedulerLock).where(SchedulerLock.lock_key == lock_key))
        if lock:
            if _ensure_utc(lock.expires_at) > current and lock.owner_id != owner_id:
                return False
            lock.owner_id = owner_id
            lock.acquired_at = current
            lock.expires_at = current + timedelta(seconds=ttl_seconds)
            self.db.flush()
            return True

        self.db.add(
            SchedulerLock(
                lock_key=lock_key,
                owner_id=owner_id,
                acquired_at=current,
                expires_at=current + timedelta(seconds=ttl_seconds),
            )
        )
        try:
            self.db.flush()
            return True
        except IntegrityError:
            self.db.rollback()
            return False

    def release_lock(self, *, lock_key: str, owner_id: str) -> None:
        self.db.execute(
            delete(SchedulerLock).where(
                SchedulerLock.lock_key == lock_key,
                SchedulerLock.owner_id == owner_id,
            )
        )
        self.db.flush()

    def find_primary_run(self, *, idempotency_key: str) -> ScheduledJobRun | None:
        return self.db.scalar(
            select(ScheduledJobRun)
            .where(ScheduledJobRun.idempotency_key == idempotency_key)
            .where(ScheduledJobRun.status.in_(["running", "success"]))
        )

    def create_attempt_run(
        self,
        *,
        job: ScheduledJob,
        idempotency_key: str,
        status: str,
        started_at: datetime,
        finished_at: datetime | None = None,
        result_json: dict[str, object] | None = None,
        error: str | None = None,
        created_task_id: int | None = None,
    ) -> ScheduledJobRun:
        run = ScheduledJobRun(
            job_id=job.id,
            job_key=job.job_key,
            idempotency_key=idempotency_key,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at) if finished_at else None,
            result_json=result_json,
            error=error,
            created_task_id=created_task_id,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def mark_run_success(
        self,
        *,
        run: ScheduledJobRun,
        finished_at: datetime,
        result_json: dict[str, object] | None,
        created_task_id: int | None = None,
    ) -> None:
        run.status = "success"
        run.finished_at = finished_at
        run.duration_ms = _duration_ms(run.started_at, finished_at)
        run.result_json = result_json
        run.created_task_id = created_task_id
        run.error = None
        self.db.flush()

    def mark_run_failed(
        self,
        *,
        run: ScheduledJobRun,
        finished_at: datetime,
        error: str,
    ) -> None:
        run.status = "failed"
        run.finished_at = finished_at
        run.duration_ms = _duration_ms(run.started_at, finished_at)
        run.error = error
        self.db.flush()

    def advance_job_after_run(self, *, job: ScheduledJob, reference: datetime | None = None) -> None:
        current = _ensure_utc(reference or utc_now())
        job.last_run_at = current
        job.next_run_at = self.compute_next_run_at(job, reference=current)
        self.db.flush()

    def compute_next_run_at(
        self,
        job: ScheduledJob,
        *,
        reference: datetime | None = None,
        initial: bool = False,
    ) -> datetime:
        current = _ensure_utc(reference or utc_now())
        if job.schedule_type == "interval":
            interval = max(int(job.interval_seconds or 30), 30)
            return current if initial else current + timedelta(seconds=interval)

        timezone_name = (job.timezone or "UTC").strip() or "UTC"
        tz = ZoneInfo(timezone_name)
        local_reference = current.astimezone(tz)
        payload = job.payload_json or {}
        run_hour = int(payload.get("hour", 0) or 0)
        run_minute = int(payload.get("minute", 0) or 0)
        if initial and local_reference.hour == run_hour:
            return current
        if (
            job.last_run_at is None
            or _ensure_utc(job.last_run_at).astimezone(tz).date() != local_reference.date()
        ) and local_reference.hour == run_hour:
            return current
        candidate = datetime.combine(
            local_reference.date(),
            time(hour=run_hour, minute=run_minute),
            tzinfo=tz,
        )
        if initial and candidate >= local_reference:
            return candidate.astimezone(timezone.utc)
        if candidate <= local_reference:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    def build_window_idempotency_key(
        self,
        *,
        job: ScheduledJob,
        scheduled_for: datetime,
    ) -> str:
        if job.schedule_type == "interval":
            interval = max(int(job.interval_seconds or 30), 30)
            bucket = int(_ensure_utc(scheduled_for).timestamp()) // interval
            return f"{job.job_key}:{interval}:{bucket}"

        timezone_name = (job.timezone or "UTC").strip() or "UTC"
        local_due = _ensure_utc(scheduled_for).astimezone(ZoneInfo(timezone_name))
        payload = job.payload_json or {}
        run_hour = int(payload.get("hour", 0) or 0)
        run_minute = int(payload.get("minute", 0) or 0)
        return f"{job.job_key}:{local_due.date().isoformat()}:{run_hour:02d}:{run_minute:02d}"


class AutonomyScheduler:
    """Production-safe scheduler with DB-backed state, locks, and history."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._owner_id = f"scheduler-{uuid.uuid4().hex[:10]}"
        self._last_daily_plan_run_at: str | None = None
        self._last_evening_review_run_at: str | None = None
        self._last_poll_run_at: str | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def owner_id(self) -> str:
        return self._owner_id

    @property
    def last_daily_plan_run_at(self) -> str | None:
        return self._job_last_run_iso(JOB_KEY_DAILY_PLAN, self._last_daily_plan_run_at)

    @property
    def last_evening_review_run_at(self) -> str | None:
        return self._job_last_run_iso(JOB_KEY_EVENING_REVIEW, self._last_evening_review_run_at)

    @property
    def last_poll_run_at(self) -> str | None:
        return self._job_last_run_iso(JOB_KEY_AUTONOMOUS_TICK, self._last_poll_run_at)

    def start(self) -> None:
        if self.running:
            return
        with get_session() as db:
            SchedulerPersistenceService(db).ensure_default_jobs()
            db.commit()
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="ai-office-autonomy")
        logger.info("autonomy.scheduler.started", owner_id=self._owner_id)

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        await self._task
        self._task = None
        logger.info("autonomy.scheduler.stopped", owner_id=self._owner_id)

    async def _run(self) -> None:
        interval = max(int(get_settings().autonomy_poll_interval_seconds), 30)
        while not self._stop_event.is_set():
            if get_autonomy_enabled():
                await self.tick_once(notify=True)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def tick_once(self, *, notify: bool = True, now: datetime | None = None) -> list[JobExecutionResult]:
        current = _ensure_utc(now or utc_now())
        with get_session() as db:
            persistence = SchedulerPersistenceService(db)
            persistence.ensure_default_jobs(now=current)
            due_jobs = [job.id for job in persistence.due_jobs(now=current)]
            db.commit()

        results: list[JobExecutionResult] = []
        for job_id in due_jobs:
            try:
                result = await self._execute_due_job(job_id=job_id, notify=notify, now=current)
            except Exception as error:  # pragma: no cover - outer safety net
                logger.error("autonomy.scheduler.tick_error", error=str(error), exc_info=True)
                result = JobExecutionResult(
                    job_key=f"job:{job_id}",
                    status="failed",
                    idempotency_key="",
                    error=str(error),
                )
            results.append(result)
        self._refresh_status_cache()
        return results

    async def _execute_due_job(
        self,
        *,
        job_id: int,
        notify: bool,
        now: datetime,
    ) -> JobExecutionResult:
        with get_session() as db:
            persistence = SchedulerPersistenceService(db)
            job = db.get(ScheduledJob, job_id)
            if not job or not job.enabled:
                return JobExecutionResult(job_key=f"job:{job_id}", status="skipped", idempotency_key="")

            job_key = job.job_key
            scheduled_for = _ensure_utc(job.next_run_at or now)
            window_key = persistence.build_window_idempotency_key(job=job, scheduled_for=scheduled_for)
            lock_acquired = persistence.acquire_lock(
                lock_key=job_key,
                owner_id=self._owner_id,
                ttl_seconds=_lock_ttl_seconds(job),
                now=now,
            )
            if not lock_acquired:
                locked_run = persistence.create_attempt_run(
                    job=job,
                    idempotency_key=f"{window_key}:locked:{uuid.uuid4().hex[:8]}",
                    status="locked",
                    started_at=now,
                    finished_at=now,
                    result_json={"reason": "lock_held", "scheduled_for": scheduled_for.isoformat()},
                )
                locked_run_id = locked_run.id
                locked_key = locked_run.idempotency_key
                locked_result = dict(locked_run.result_json or {})
                db.commit()
                return JobExecutionResult(
                    job_key=job_key,
                    status="locked",
                    idempotency_key=locked_key,
                    run_id=locked_run_id,
                    result_json=locked_result,
                )

            existing = persistence.find_primary_run(idempotency_key=window_key)
            if existing:
                skipped_run = persistence.create_attempt_run(
                    job=job,
                    idempotency_key=f"{window_key}:skipped:{uuid.uuid4().hex[:8]}",
                    status="skipped",
                    started_at=now,
                    finished_at=now,
                    result_json={
                        "reason": "idempotency_conflict",
                        "existing_run_id": existing.id,
                        "scheduled_for": scheduled_for.isoformat(),
                    },
                )
                skipped_run_id = skipped_run.id
                skipped_key = skipped_run.idempotency_key
                skipped_result = dict(skipped_run.result_json or {})
                if existing.status == "success":
                    persistence.advance_job_after_run(job=job, reference=now)
                db.commit()
                self._release_lock(job_key)
                return JobExecutionResult(
                    job_key=job_key,
                    status="skipped",
                    idempotency_key=skipped_key,
                    run_id=skipped_run_id,
                    result_json=skipped_result,
                )

            running_run = persistence.create_attempt_run(
                job=job,
                idempotency_key=window_key,
                status="running",
                started_at=now,
                result_json={"scheduled_for": scheduled_for.isoformat()},
            )
            running_run_id = running_run.id
            db.commit()

        try:
            with get_session() as db:
                persistence = SchedulerPersistenceService(db)
                job = db.get(ScheduledJob, job_id)
                run = db.get(ScheduledJobRun, running_run_id)
                if not job or not run:
                    raise RuntimeError(f"Scheduler job/run disappeared for job_id={job_id}")

                result_json, created_task_id = await self._run_job(job_key, db=db, notify=notify)
                finished_at = max(_ensure_utc(utc_now()), now)
                persistence.mark_run_success(
                    run=run,
                    finished_at=finished_at,
                    result_json=result_json,
                    created_task_id=created_task_id,
                )
                persistence.advance_job_after_run(job=job, reference=finished_at)
                audit_log(
                    db,
                    actor_type="scheduler",
                    actor_id=self._owner_id,
                    action="scheduler.job_succeeded",
                    object_type="scheduled_job_run",
                    object_id=run.id,
                    metadata={"job_key": job_key, "idempotency_key": window_key},
                )
                db.commit()
                self._update_cached_status(job_key, finished_at)
                return JobExecutionResult(
                    job_key=job_key,
                    status="success",
                    idempotency_key=window_key,
                    run_id=run.id,
                    result_json=result_json,
                )
        except Exception as error:
            finished_at = max(_ensure_utc(utc_now()), now)
            with get_session() as db:
                persistence = SchedulerPersistenceService(db)
                job = db.get(ScheduledJob, job_id)
                run = db.get(ScheduledJobRun, running_run_id)
                if run:
                    persistence.mark_run_failed(run=run, finished_at=finished_at, error=str(error))
                if job:
                    persistence.advance_job_after_run(job=job, reference=finished_at)
                audit_log(
                    db,
                    actor_type="scheduler",
                    actor_id=self._owner_id,
                    action="scheduler.job_failed",
                    object_type="scheduled_job_run",
                    object_id=running_run_id,
                    metadata={"job_key": job_key, "error": str(error)},
                )
                db.commit()
            logger.error("autonomy.scheduler.job_error", job_id=job_id, error=str(error), exc_info=True)
            return JobExecutionResult(
                job_key=job_key,
                status="failed",
                idempotency_key=window_key,
                run_id=running_run_id,
                error=str(error),
            )
        finally:
            self._release_lock(job_key)

    async def _run_job(
        self,
        job_key: str,
        *,
        db: Session,
        notify: bool,
    ) -> tuple[dict[str, object], int | None]:
        service = AutonomyService(db)
        if job_key == JOB_KEY_DAILY_PLAN:
            result = await service.daily_plan(notify=notify)
            payload = result.model_dump()
            task_ids = list(payload.get("created_task_ids", []) or [])
            return payload, int(task_ids[0]) if task_ids else None
        if job_key == JOB_KEY_EVENING_REVIEW:
            result = await service.evening_review(notify=notify)
            return result, None
        if job_key == JOB_KEY_AUTONOMOUS_TICK:
            result = await service.poll_queued_tasks(notify=notify)
            completed = list(result.get("completed", []) or [])
            return result, int(completed[0]) if completed else None
        raise ValueError(f"Unknown scheduled job: {job_key}")

    def _release_lock(self, job_key: str) -> None:
        with get_session() as db:
            SchedulerPersistenceService(db).release_lock(lock_key=job_key, owner_id=self._owner_id)
            db.commit()

    def _refresh_status_cache(self) -> None:
        with get_session() as db:
            service = SchedulerPersistenceService(db)
            for job_key in [JOB_KEY_DAILY_PLAN, JOB_KEY_EVENING_REVIEW, JOB_KEY_AUTONOMOUS_TICK]:
                job = service.get_job_by_key(job_key)
                if not job or not job.last_run_at:
                    continue
                self._update_cached_status(job_key, job.last_run_at)

    def _update_cached_status(self, job_key: str, executed_at: datetime) -> None:
        value = _ensure_utc(executed_at).isoformat(timespec="seconds")
        if job_key == JOB_KEY_DAILY_PLAN:
            self._last_daily_plan_run_at = value
        elif job_key == JOB_KEY_EVENING_REVIEW:
            self._last_evening_review_run_at = value
        elif job_key == JOB_KEY_AUTONOMOUS_TICK:
            self._last_poll_run_at = value

    def _job_last_run_iso(self, job_key: str, fallback: str | None) -> str | None:
        try:
            with get_session() as db:
                job = SchedulerPersistenceService(db).get_job_by_key(job_key)
                if job and job.last_run_at:
                    return _ensure_utc(job.last_run_at).isoformat(timespec="seconds")
        except Exception:
            return fallback
        return fallback


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _duration_ms(started_at: datetime, finished_at: datetime | None) -> int | None:
    if finished_at is None:
        return None
    delta = _ensure_utc(finished_at) - _ensure_utc(started_at)
    return max(int(delta.total_seconds() * 1000), 0)


def _lock_ttl_seconds(job: ScheduledJob) -> int:
    if job.schedule_type == "interval":
        return max(min(int(job.interval_seconds or 300) * 2, 3600), 300)
    return 1800


autonomy_scheduler = AutonomyScheduler()
