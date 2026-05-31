from fastapi.testclient import TestClient

import web.app as web_app
from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.schemas import TaskCreate
from services.task_service import TaskService
from tools.base import ToolContext
from tools.registry import ToolExecutionService


def test_github_write_without_approval_creates_pending_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'approval.db'}")
    monkeypatch.setenv("AI_OFFICE_REQUIRE_API_KEY", "false")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()

    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Create issue", input_text="Создай GitHub issue"))
        result = ToolExecutionService(db).call_tool(
            "github.issue.create",
            {"title": "Fix RAG namespace isolation", "body": "Details"},
            ToolContext(task_id=task.id, workspace_id="default", agent_name="developer"),
        )

        assert result.requires_approval is True
        assert result.approval_id is not None
        assert TaskService(db).get_task(task.id).status == "waiting_approval"


def test_approval_decision_requires_permission(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'rbac.db'}")
    monkeypatch.setenv("AI_OFFICE_REQUIRE_API_KEY", "false")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()

    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Create issue", input_text="Создай GitHub issue"))
        result = ToolExecutionService(db).call_tool(
            "github.issue.create",
            {"title": "Fix", "body": "Details"},
            ToolContext(task_id=task.id, workspace_id="default", agent_name="developer"),
        )

    client = TestClient(web_app.app)
    denied = client.post(
        f"/api/approvals/{result.approval_id}/approve",
        headers={"X-User-Role": "viewer"},
        json={"approved_by": "viewer"},
    )
    assert denied.status_code == 403

    allowed = client.post(
        f"/api/approvals/{result.approval_id}/approve",
        headers={"X-User-Role": "manager"},
        json={"approved_by": "manager"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "approved"
