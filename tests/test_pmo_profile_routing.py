from __future__ import annotations

import pytest

from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.schemas import ProjectCreate, TaskCreate
from services.approval_service import ApprovalService
from services.autonomy_service import AutonomyService
from services.pmo_planner import PMOPlanningService
from services.project_service import ProjectService
from services.task_service import TaskService


def configure_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OFFICE_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'profiles.db'}")
    monkeypatch.setenv("AUTONOMY_ENABLED", "false")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()


def test_pmo_fallback_attaches_profile_metadata():
    plan = PMOPlanningService().plan_from_text(
        goal="Build an MCP tool server for AI Office",
        project_slug="ai-office",
        llm_text="not-json",
    )

    task = plan.tasks[0]
    assert task.profile_id == "developer.mcp_builder"
    assert task.profile_name == "MCP Builder"
    assert task.base_agent == "developer"


def test_task_creation_records_profile_metadata_in_event(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        project = ProjectService(db).create_project(
            ProjectCreate(slug="ai-office", name="AI Office")
        )
        task = TaskService(db).create_task(
            TaskCreate(
                project_id=project.id,
                title="Build MCP tool server",
                assigned_agent="developer",
                base_agent="developer",
                profile_id="developer.mcp_builder",
                profile_name="MCP Builder",
            )
        )
        events = TaskService(db).list_events(task.id)

    created_event = next(event for event in events if event.event_type == "task_created")
    assert created_event.metadata_json["profile_id"] == "developer.mcp_builder"
    assert created_event.metadata_json["profile_name"] == "MCP Builder"


@pytest.mark.asyncio
async def test_dangerous_action_with_developer_profile_still_requires_approval(tmp_path, monkeypatch):
    configure_runtime(monkeypatch, tmp_path)
    with get_session() as db:
        project = ProjectService(db).create_project(
            ProjectCreate(slug="ai-office", name="AI Office")
        )
        task = TaskService(db).create_task(
            TaskCreate(
                project_id=project.id,
                title="Deploy to production",
                description="Deploy and push to main",
                status="queued",
                assigned_agent="developer",
                base_agent="developer",
                profile_id="developer.devops_automator",
                profile_name="DevOps Automator",
            )
        )

        result = await AutonomyService(db).poll_queued_tasks(notify=False)
        refreshed = TaskService(db).get_task(task.id)

        assert task.id in result["waiting_approval"]
        assert refreshed is not None
        assert refreshed.status == "waiting_approval"
        assert ApprovalService(db).list_approvals(status="pending")
