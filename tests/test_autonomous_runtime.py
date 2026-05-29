from __future__ import annotations

from datetime import timedelta

from alembic import command
from alembic.config import Config
import pytest
from fastapi.testclient import TestClient

import web.app as web_app
from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.models import utc_now
from core.schemas import ApprovalCreate, ProjectCreate, TaskCreate, TaskEventCreate
from services.approval_service import ApprovalService, ApprovalStateError
from services.autonomy_service import AutonomyService
from services.project_service import ProjectService
from services.task_service import TaskService


def configure_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OFFICE_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("AI_OFFICE_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'runtime.db'}")
    monkeypatch.setenv("AUTONOMY_ENABLED", "false")
    monkeypatch.setenv("AI_OFFICE_TASK_STUCK_TIMEOUT_MINUTES", "30")
    monkeypatch.setenv("AI_OFFICE_TASK_MAX_RETRIES", "2")
    monkeypatch.setenv("AI_OFFICE_APPROVAL_TTL_HOURS", "24")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    return {"X-API-Key": "test-key"}


def test_api_key_is_disabled_by_default_for_personal_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'runtime-no-key.db'}")
    monkeypatch.delenv("AI_OFFICE_REQUIRE_API_KEY", raising=False)
    monkeypatch.delenv("AI_OFFICE_API_KEY", raising=False)
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    client = TestClient(web_app.app)

    response = client.get("/api/projects")

    assert response.status_code == 200


def test_private_autonomous_api_requires_key(tmp_path, monkeypatch):
    headers = configure_runtime(monkeypatch, tmp_path)
    client = TestClient(web_app.app)

    missing_key = client.get("/api/projects")
    assert missing_key.status_code == 401

    invalid = client.get("/api/projects", headers={"X-API-Key": "wrong"})
    assert invalid.status_code == 401

    allowed = client.get("/api/projects", headers=headers)
    assert allowed.status_code == 200

    bearer = client.get("/api/projects", headers={"Authorization": "Bearer test-key"})
    assert bearer.status_code == 200


def test_legacy_private_api_requires_key(tmp_path, monkeypatch):
    headers = configure_runtime(monkeypatch, tmp_path)
    client = TestClient(web_app.app)

    assert client.get("/api/conversations").status_code == 401
    assert client.get("/api/conversations", headers=headers).status_code == 200


def test_task_engine_project_task_events_and_approvals(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        project = ProjectService(db).create_project(
            ProjectCreate(slug="ai-office", name="AI Office", goal="Autonomous core")
        )
        task = TaskService(db).create_task(
            TaskCreate(
                project_id=project.id,
                title="Add task engine tests",
                assigned_agent="developer",
            )
        )
        updated = TaskService(db).update_status(task.id, "queued")
        assert updated is not None
        assert updated.status == "queued"

        event = TaskService(db).add_event(
            task.id,
            TaskEventCreate(event_type="note", message="Ready"),
        )
        assert event.id

        approval = ApprovalService(db).create_approval(
            ApprovalCreate(
                task_id=task.id,
                action_type="deploy",
                summary="Deploy requires approval",
                requested_by_agent="developer",
            )
        )
        approved = ApprovalService(db).approve(approval.id, approved_by="owner")
        assert approved is not None
        assert approved.status == "approved"

        second = ApprovalService(db).create_approval(
            ApprovalCreate(task_id=task.id, action_type="send_email", summary="Send email")
        )
        rejected = ApprovalService(db).reject(second.id, approved_by="owner")
        assert rejected is not None
        assert rejected.status == "rejected"


def test_alembic_initial_migration_runs(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_engine()

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    assert db_path.exists()
    reset_db_engine()
    with get_session() as db:
        projects = ProjectService(db).list_projects()
        assert projects == []


@pytest.mark.asyncio
async def test_daily_plan_creates_tasks_and_events(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    sent: list[str] = []

    async def fake_notify(text: str) -> bool:
        sent.append(text)
        return True

    with get_session() as db:
        result = await AutonomyService(db, notifier=fake_notify).daily_plan(notify=True)
        assert result.created_task_ids
        first_task_id = result.created_task_ids[0]
        events = TaskService(db).list_events(first_task_id)
        assert any(event.event_type == "daily_plan_created" for event in events)
        assert sent


@pytest.mark.asyncio
async def test_task_polling_requires_approval_for_dangerous_task(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        project = ProjectService(db).create_project(ProjectCreate(slug="ai-office", name="AI Office"))
        task = TaskService(db).create_task(
            TaskCreate(
                project_id=project.id,
                title="Deploy to production",
                description="Deploy current code to prod",
                status="queued",
                assigned_agent="developer",
            )
        )

        result = await AutonomyService(db).poll_queued_tasks(notify=False)
        assert task.id in result["waiting_approval"]
        refreshed = TaskService(db).get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == "waiting_approval"
        assert ApprovalService(db).list_approvals(status="pending")


@pytest.mark.asyncio
async def test_task_polling_saves_completed_result(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        project = ProjectService(db).create_project(ProjectCreate(slug="ai-office", name="AI Office"))
        task = TaskService(db).create_task(
            TaskCreate(
                project_id=project.id,
                title="Write a safe status report",
                status="queued",
                assigned_agent="pmo",
            )
        )

        result = await AutonomyService(db).poll_queued_tasks(notify=False)
        assert task.id in result["completed"]
        refreshed = TaskService(db).get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == "completed"
        assert refreshed.result_summary


def test_running_task_below_timeout_remains_running(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Still running", status="running"))
        task.started_at = utc_now() - timedelta(minutes=5)
        db.commit()

        result = TaskService(db).detect_stuck_tasks(timeout_minutes=30, max_retries=2)
        refreshed = TaskService(db).get_task(task.id)
        assert result == {"requeued": [], "stuck": []}
        assert refreshed is not None
        assert refreshed.status == "running"


def test_running_task_above_timeout_with_retries_returns_to_queued(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Retry stuck", status="running"))
        task.started_at = utc_now() - timedelta(minutes=60)
        task.retry_count = 0
        db.commit()

        result = TaskService(db).detect_stuck_tasks(timeout_minutes=30, max_retries=2)
        refreshed = TaskService(db).get_task(task.id)
        events = TaskService(db).list_events(task.id)
        assert result["requeued"] == [task.id]
        assert refreshed is not None
        assert refreshed.status == "queued"
        assert refreshed.retry_count == 1
        assert any(event.event_type == "task_retry_queued" for event in events)


def test_running_task_above_timeout_without_retries_becomes_stuck(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="No retry stuck", status="running"))
        task.started_at = utc_now() - timedelta(minutes=60)
        task.retry_count = 2
        db.commit()

        result = TaskService(db).detect_stuck_tasks(timeout_minutes=30, max_retries=2)
        refreshed = TaskService(db).get_task(task.id)
        assert result["stuck"] == [task.id]
        assert refreshed is not None
        assert refreshed.status == "stuck"


def test_failed_task_retries_until_budget(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Retry failed", status="failed"))
        task.retry_count = 0
        db.commit()

        retried = TaskService(db).retry_failed_tasks()
        refreshed = TaskService(db).get_task(task.id)
        assert retried == [task.id]
        assert refreshed is not None
        assert refreshed.status == "queued"
        assert refreshed.retry_count == 1


def test_failed_task_does_not_retry_after_max(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Max failed", status="failed"))
        task.retry_count = 2
        db.commit()

        retried = TaskService(db).retry_failed_tasks()
        refreshed = TaskService(db).get_task(task.id)
        assert retried == []
        assert refreshed is not None
        assert refreshed.status == "failed"


def test_approval_expiration_changes_task_and_blocks_approval(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Wait approval", status="waiting_approval"))
        approval = ApprovalService(db).create_approval(
            ApprovalCreate(task_id=task.id, action_type="deploy", summary="Need approval")
        )
        approval.created_at = utc_now() - timedelta(hours=25)
        db.commit()

        expired_ids = ApprovalService(db).expire_pending(ttl_hours=24)
        db.refresh(approval)
        refreshed = TaskService(db).get_task(task.id)
        assert expired_ids == [approval.id]
        assert approval.status == "expired"
        assert refreshed is not None
        assert refreshed.status == "cancelled"
        with pytest.raises(ApprovalStateError):
            ApprovalService(db).approve(approval.id)


def test_non_expired_approval_remains_pending(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        approval = ApprovalService(db).create_approval(
            ApprovalCreate(action_type="deploy", summary="Need approval")
        )

        expired_ids = ApprovalService(db).expire_pending(ttl_hours=24)
        db.refresh(approval)
        assert expired_ids == []
        assert approval.status == "pending"


def test_autonomous_status_endpoint_and_health_do_not_leak_secrets(tmp_path, monkeypatch):
    headers = configure_runtime(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-value")
    get_settings.cache_clear()
    client = TestClient(web_app.app)

    status = client.get("/api/autonomous/status", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert "scheduler" in body
    assert "tasks" in body
    assert "database" in body

    health = client.get("/health")
    assert health.status_code == 200
    health_text = health.text
    assert "sk-test-secret-value" not in health_text
    assert health.json()["model_keys"]["openai"] is True
