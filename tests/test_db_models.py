from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.models import AuditEvent, TaskRun, Workspace
from core.schemas import TaskCreate
from services.task_service import TaskService


def test_p0_models_create_task_run_and_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p0.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()

    with get_session() as db:
        task = TaskService(db).create_task(
            TaskCreate(title="P0 task", input_text="safe input", workspace_id="default")
        )
        run = TaskRun(task_id=task.id, status="completed", trace_id="trace")
        audit = AuditEvent(
            workspace_id="default",
            task_id=task.id,
            actor_type="system",
            actor_id="test",
            action="task.completed",
            object_type="task",
            object_id=str(task.id),
            metadata_json={},
        )
        db.add_all([run, audit])
        db.commit()

        assert db.get(Workspace, "default") is not None
        assert run.id
        assert audit.id
