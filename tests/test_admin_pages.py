from fastapi.testclient import TestClient

import web.app as web_app
from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.schemas import TaskCreate
from services.task_service import TaskService
from tools.base import ToolContext
from tools.registry import ToolExecutionService


def test_admin_pages_open_and_show_pending_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'admin.db'}")
    monkeypatch.setenv("AI_OFFICE_REQUIRE_API_KEY", "false")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()

    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Admin task", input_text="Создай GitHub issue"))
        task_id = task.id
        ToolExecutionService(db).call_tool(
            "github.issue.create",
            {"title": "Admin approval", "body": "Details"},
            ToolContext(task_id=task.id, workspace_id="default", agent_name="developer"),
        )

    client = TestClient(web_app.app)
    assert client.get("/admin/tasks").status_code == 200
    detail = client.get(f"/admin/tasks/{task_id}")
    assert detail.status_code == 200
    assert "Admin task" in detail.text
    approvals = client.get("/admin/approvals")
    assert approvals.status_code == 200
    assert "pending" in approvals.text
    assert client.get("/admin/audit").status_code == 200
    assert client.get("/admin/costs").status_code == 200
    assert client.get("/admin/knowledge").status_code == 200
