from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.models import ModelUsage, TaskRun
from core.schemas import TaskCreate
from services.task_service import TaskService
from workers.queue import enqueue_task
from workers.tasks import execute_task


def test_worker_completes_safe_task_and_records_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'worker.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_PRIMARY", "fake")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()

    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Worker task", input_text="My email test@example.com"))
        enqueue_task(db, task.id)

        result = execute_task(db, task.id)

        assert result["status"] == "completed"
        assert db.get(TaskRun, result["task_run_id"]).status == "completed"
        assert db.query(ModelUsage).count() == 1
        refreshed = TaskService(db).get_task(task.id)
        assert refreshed.result_payload["redacted_model_input_hash"]
