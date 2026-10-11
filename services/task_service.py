"""Task engine operations for projects, events, agent runs, and approvals."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.action_policy import classify_task
from core.config import get_settings
from core.models import AgentRun, Approval, Task, TaskEvent, Workspace, utc_now
from core.schemas import TaskCreate, TaskEventCreate
from core.task_lifecycle import (
    OPEN_TASK_STATUSES,
    TASK_CANCELLED,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_QUEUED,
    TASK_RUNNING,
    TASK_STUCK,
    TASK_WAITING_APPROVAL,
    is_older_than,
)
from services.project_service import ProjectService


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_task(self, payload: TaskCreate) -> Task:
        self._ensure_workspace(payload.workspace_id)
        project_id = payload.project_id
        if payload.project_slug:
            project = ProjectService(self.db).get_project_by_slug(payload.project_slug)
            if project:
                project_id = project.id

        task = Task(
            workspace_id=payload.workspace_id,
            project_id=project_id,
            title=payload.title,
            input_text=payload.input_text or payload.description or payload.title,
            description=payload.description or payload.input_text,
            created_by=payload.created_by,
            assigned_agent=payload.agent_hint or payload.assigned_agent,
            status=payload.status,
            risk_level=payload.risk_level,
            priority=payload.priority,
            requires_approval=payload.requires_approval,
            due_at=payload.due_at,
        )
        self.db.add(task)
        self.db.flush()
        self.add_event(
            task.id,
            TaskEventCreate(
                event_type="task_created",
                message=f"Task created by {payload.created_by}.",
                metadata={
                    "assigned_agent": payload.assigned_agent,
                    "requires_approval": payload.requires_approval,
                    "base_agent": payload.base_agent,
                    "profile_id": payload.profile_id,
                    "profile_name": payload.profile_name,
                },
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def _ensure_workspace(self, workspace_id: str | None = None) -> Workspace:
        workspace_key = (workspace_id or "default").strip() or "default"
        workspace = self.db.get(Workspace, workspace_key)
        if workspace:
            return workspace
        workspace = Workspace(id=workspace_key, name="Default workspace" if workspace_key == "default" else workspace_key)
        self.db.add(workspace)
        self.db.flush()
        return workspace

    def list_tasks(
        self,
        *,
        status: str | None = None,
        project_id: int | None = None,
        project_slug: str | None = None,
        assigned_agent: str | None = None,
        open_only: bool = False,
    ) -> list[Task]:
        query = select(Task).order_by(Task.priority.asc(), Task.updated_at.desc())
        if open_only:
            query = query.where(Task.status.in_(OPEN_TASK_STATUSES))
        if status:
            query = query.where(Task.status == status)
        if project_slug:
            project = ProjectService(self.db).get_project_by_slug(project_slug)
            if not project:
                return []
            project_id = project.id
        if project_id is not None:
            query = query.where(Task.project_id == project_id)
        if assigned_agent:
            query = query.where(Task.assigned_agent == assigned_agent)
        return list(self.db.scalars(query))

    def get_task(self, task_id: int) -> Task | None:
        return self.db.get(Task, task_id)

    def update_status(self, task_id: int, status: str, *, message: str = "") -> Task | None:
        task = self.get_task(task_id)
        if not task:
            return None
        self._apply_status(task, status, message=message)
        self.db.commit()
        self.db.refresh(task)
        return task

    def add_event(
        self,
        task_id: int,
        payload: TaskEventCreate,
        *,
        commit: bool = True,
    ) -> TaskEvent:
        event = TaskEvent(
            task_id=task_id,
            event_type=payload.event_type,
            message=payload.message,
            metadata_json=payload.metadata,
        )
        self.db.add(event)
        if commit:
            self.db.commit()
            self.db.refresh(event)
        return event

    def list_events(self, task_id: int) -> list[TaskEvent]:
        query = (
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id)
            .order_by(TaskEvent.created_at.asc())
        )
        return list(self.db.scalars(query))

    def queue_task(self, task_id: int) -> Task | None:
        return self.update_status(task_id, TASK_QUEUED, message="Task queued for autonomous runtime.")

    def save_result(
        self,
        task_id: int,
        *,
        summary: str,
        payload: dict[str, Any] | None = None,
        status: str = "completed",
    ) -> Task | None:
        task = self.get_task(task_id)
        if not task:
            return None
        task.result_summary = summary
        task.result_payload = payload or {}
        self._apply_status(task, status, message=f"Result saved with status {status}.")
        self.add_event(
            task_id,
            TaskEventCreate(
                event_type="result_saved",
                message=summary[:800],
                metadata={"status": status},
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def run_task(self, task_id: int) -> dict[str, Any] | None:
        """Run a task in safe MVP mode and persist agent run/result."""
        task = self.get_task(task_id)
        if not task:
            return None

        policy = classify_task(
            task.title,
            task.description,
            requires_approval=task.requires_approval,
        )
        if policy.requires_approval:
            approval = Approval(
                task_id=task.id,
                action_type="run_task",
                summary=f"Approval required before running task: {task.title}",
                payload={
                    "task_id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "policy_reason": policy.reason,
                },
                requested_by_agent=task.assigned_agent,
            )
            self._apply_status(
                task,
                TASK_WAITING_APPROVAL,
                message=f"Approval required before running task: {task.title}",
            )
            task.requires_approval = True
            self.db.add(approval)
            self.add_event(
                task.id,
                TaskEventCreate(
                    event_type="approval_requested",
                    message=approval.summary,
                    metadata={"approval_action": "run_task", "policy_reason": policy.reason},
                ),
                commit=False,
            )
            self.db.commit()
            self.db.refresh(approval)
            self.db.refresh(task)
            return {
                "status": TASK_WAITING_APPROVAL,
                "approval_id": approval.id,
                "task_id": task.id,
            }

        now = utc_now()
        self._apply_status(task, TASK_RUNNING, message="Task execution started.")
        task.started_at = task.started_at or now
        agent_run = AgentRun(
            task_id=task.id,
            agent_id=task.assigned_agent,
            status="running",
            input={"title": task.title, "description": task.description},
            started_at=now,
        )
        self.db.add(agent_run)
        self.db.flush()

        result_summary = (
            f"Draft result prepared by {task.assigned_agent}: {task.title}. "
            "This autonomous MVP records safe planning/results without external side effects."
        )
        agent_run.status = "completed"
        agent_run.output = {"summary": result_summary, "mode": "safe_draft"}
        agent_run.completed_at = utc_now()
        self._apply_status(task, TASK_COMPLETED, message="Task execution completed.")
        task.completed_at = agent_run.completed_at
        task.result_summary = result_summary
        task.result_payload = agent_run.output
        self.add_event(
            task.id,
            TaskEventCreate(
                event_type="task_completed",
                message=result_summary,
                metadata={"agent_run_id": agent_run.id, "mode": "safe_draft"},
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(task)
        self.db.refresh(agent_run)
        return {
            "status": TASK_COMPLETED,
            "task_id": task.id,
            "agent_run_id": agent_run.id,
            "result_summary": result_summary,
        }

    def list_tasks_since(self, since: datetime) -> list[Task]:
        query = select(Task).where(Task.updated_at >= since).order_by(Task.updated_at.desc())
        return list(self.db.scalars(query))

    def retry_task(self, task_id: int, *, reason: str = "") -> Task | None:
        """Move a failed/stuck task back to queued if retry budget remains."""
        task = self.get_task(task_id)
        if not task:
            return None
        max_retries = max(get_settings().ai_office_task_max_retries, 0)
        if task.retry_count >= max_retries:
            return task

        task.retry_count += 1
        self._apply_status(
            task,
            TASK_QUEUED,
            message=reason or f"Retry {task.retry_count}/{max_retries} queued.",
            metadata={"retry_count": task.retry_count, "max_retries": max_retries},
        )
        self.add_event(
            task.id,
            TaskEventCreate(
                event_type="task_retry_queued",
                message=reason or f"Retry {task.retry_count}/{max_retries} queued.",
                metadata={"retry_count": task.retry_count, "max_retries": max_retries},
            ),
            commit=False,
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def retry_failed_tasks(self) -> list[int]:
        """Queue retryable failed tasks within the configured retry budget."""
        retried: list[int] = []
        failed_tasks = self.list_tasks(status=TASK_FAILED)
        for task in failed_tasks:
            before = task.retry_count
            updated = self.retry_task(task.id, reason="Failed task returned to queue for retry.")
            if updated and updated.retry_count > before and updated.status == TASK_QUEUED:
                retried.append(task.id)
        return retried

    def detect_stuck_tasks(
        self,
        *,
        timeout_minutes: int | None = None,
        max_retries: int | None = None,
    ) -> dict[str, list[int]]:
        """Recover or mark running tasks that exceeded the stuck timeout."""
        settings = get_settings()
        timeout = timeout_minutes if timeout_minutes is not None else settings.ai_office_task_stuck_timeout_minutes
        retry_budget = max_retries if max_retries is not None else settings.ai_office_task_max_retries
        running_tasks = self.list_tasks(status=TASK_RUNNING)
        requeued: list[int] = []
        stuck: list[int] = []

        for task in running_tasks:
            started_at = task.started_at or task.updated_at
            if not is_older_than(started_at, minutes=timeout):
                continue
            if task.retry_count < retry_budget:
                task.retry_count += 1
                self._apply_status(
                    task,
                    TASK_QUEUED,
                    message=f"Task exceeded {timeout} minutes and was queued for retry.",
                    metadata={
                        "retry_count": task.retry_count,
                        "max_retries": retry_budget,
                        "timeout_minutes": timeout,
                    },
                )
                self.add_event(
                    task.id,
                    TaskEventCreate(
                        event_type="task_retry_queued",
                        message=f"Stuck task retry {task.retry_count}/{retry_budget} queued.",
                        metadata={"retry_count": task.retry_count, "max_retries": retry_budget},
                    ),
                    commit=False,
                )
                requeued.append(task.id)
            else:
                self._apply_status(
                    task,
                    TASK_STUCK,
                    message=f"Task exceeded {timeout} minutes and has no retries remaining.",
                    metadata={"retry_count": task.retry_count, "max_retries": retry_budget},
                )
                stuck.append(task.id)

        if requeued or stuck:
            self.db.commit()
        return {"requeued": requeued, "stuck": stuck}

    def count_by_status(self) -> dict[str, int]:
        rows = self.db.execute(select(Task.status, func.count(Task.id)).group_by(Task.status)).all()
        return {str(status): int(count) for status, count in rows}

    def completed_today_count(self) -> int:
        now = utc_now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(
            self.db.scalar(
                select(func.count(Task.id)).where(
                    Task.status == TASK_COMPLETED,
                    Task.completed_at >= start,
                )
            )
            or 0
        )

    def _apply_status(
        self,
        task: Task,
        status: str,
        *,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        previous_status = task.status
        task.status = status
        if status == TASK_RUNNING and task.started_at is None:
            task.started_at = utc_now()
        if status in {TASK_COMPLETED, TASK_FAILED, TASK_CANCELLED, TASK_STUCK}:
            task.completed_at = utc_now()
        if status == TASK_QUEUED:
            task.started_at = None
            task.completed_at = None

        self.add_event(
            task.id,
            TaskEventCreate(
                event_type="status_changed",
                message=message or f"Status changed from {previous_status} to {status}.",
                metadata={
                    "from_status": previous_status,
                    "to_status": status,
                    **(metadata or {}),
                },
            ),
            commit=False,
        )
