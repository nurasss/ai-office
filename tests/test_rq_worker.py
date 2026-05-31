from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.schemas import TaskCreate
from services.task_service import TaskService
from workers.rq_queue import enqueue_task_rq, process_task_job


def test_rq_enqueue_falls_back_when_redis_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'rq.db'}")
    monkeypatch.setenv("WORKER_BACKEND", "redis")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    monkeypatch.setattr("workers.rq_queue.redis_connected", lambda: False)

    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="RQ fallback", input_text="safe"))

    job_id = enqueue_task_rq(task.id)

    assert job_id == f"db:{task.id}"


def test_process_task_job_executes_existing_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'rq-job.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_PRIMARY", "fake")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()

    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="RQ job", input_text="safe"))

    result = process_task_job(task.id)

    assert result["status"] == "completed"
