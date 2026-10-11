"""Redis/RQ queue integration with DB-backed fallback."""

from __future__ import annotations

from typing import Any

from core.config import get_settings
from core.db import get_session, redis_connected
from services.audit_service import audit_log
from workers.queue import enqueue_task
from workers.tasks import execute_task


def enqueue_task_rq(task_id: int) -> str:
    """Enqueue task in Redis/RQ when available, otherwise use DB fallback."""
    settings = get_settings()
    backend = settings.worker_backend.strip().lower()
    if backend == "redis" and redis_connected():
        try:
            from redis import Redis
            from rq import Queue

            connection = Redis.from_url(settings.redis_url)
            queue = Queue(settings.rq_queue_name, connection=connection)
            job = queue.enqueue(process_task_job, task_id)
            with get_session() as db:
                audit_log(
                    db,
                    workspace_id="default",
                    task_id=task_id,
                    actor_type="system",
                    actor_id="rq",
                    action="task.enqueued",
                    object_type="task",
                    object_id=task_id,
                    metadata={"backend": "redis", "queue": settings.rq_queue_name, "job_id": job.id},
                    commit=True,
                )
            return str(job.id)
        except Exception:
            # Fall through to the local DB marker. The API path must keep
            # accepting tasks even when Redis is down or misconfigured.
            pass

    with get_session() as db:
        enqueue_task(db, task_id)
        audit_log(
            db,
            workspace_id="default",
            task_id=task_id,
            actor_type="system",
            actor_id="db_queue",
            action="task.enqueued",
            object_type="task",
            object_id=task_id,
            metadata={"backend": "db_fallback"},
            commit=True,
        )
    return f"db:{task_id}"


def process_task_job(task_id: int) -> dict[str, Any]:
    """RQ job entrypoint."""
    with get_session() as db:
        result = execute_task(db, task_id)
        return result or {"status": "not_found", "task_id": task_id}
