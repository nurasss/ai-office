"""Daily planning, task polling, and review loops for the personal runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, time, timezone
from typing import Any

from sqlalchemy.orm import Session

from core.action_policy import classify_task
from core.config import get_settings
from core.models import Task
from core.schemas import DailyPlanResponse, ProjectCreate, TaskCreate, TaskEventCreate
from services.approval_service import ApprovalService
from services.memory_service import MemoryService
from services.pmo_planner import PMOPlanningService
from services.project_service import ProjectService
from services.task_service import TaskService
from tools.external.telegram import send_telegram_approval_request, send_telegram_message

Notifier = Callable[[str], Awaitable[bool]]

_autonomy_enabled_override: bool | None = None


def set_autonomy_enabled(enabled: bool) -> None:
    global _autonomy_enabled_override
    _autonomy_enabled_override = enabled


def get_autonomy_enabled() -> bool:
    if _autonomy_enabled_override is not None:
        return _autonomy_enabled_override
    return bool(get_settings().autonomy_enabled)


class AutonomyService:
    def __init__(
        self,
        db: Session,
        *,
        notifier: Notifier | None = None,
    ) -> None:
        self.db = db
        self.projects = ProjectService(db)
        self.tasks = TaskService(db)
        self.approvals = ApprovalService(db)
        self.memory = MemoryService(db)
        self.planner = PMOPlanningService()
        self.notifier = notifier or send_telegram_message

    async def daily_plan(self, *, notify: bool = True) -> DailyPlanResponse:
        projects = self.projects.list_projects(status="active")
        if not projects:
            projects = self.projects.ensure_default_projects()

        created_task_ids: list[int] = []
        summary_lines = ["Доброе утро. Я проверил активные проекты."]

        for project in projects:
            open_tasks = self.tasks.list_tasks(project_id=project.id, open_only=True)
            memories = self.memory.latest_for_project(project.slug, limit=3)
            memory_context = "\n".join(memory.content for memory in memories)
            goal = project.goal or f"Move {project.name} forward safely."
            if open_tasks:
                summary_lines.append(
                    f"{project.name}: открытых задач {len(open_tasks)}. Следующий шаг: продолжить приоритетные задачи."
                )
                continue

            plan = self.planner.plan_from_text(
                goal=f"{goal}\n\nКонтекст памяти:\n{memory_context}".strip(),
                project_slug=project.slug,
            )
            summary_lines.append(f"{project.name}: создан план PMO для следующего шага.")
            for item in plan.tasks:
                task = self.tasks.create_task(
                    TaskCreate(
                        project_id=project.id,
                        title=item.title,
                        description=item.description,
                        created_by="pmo",
                        assigned_agent=item.assigned_agent,
                        status="queued",
                        priority=item.priority,
                        requires_approval=item.requires_approval,
                        base_agent=item.base_agent,
                        profile_id=item.profile_id,
                        profile_name=item.profile_name,
                    )
                )
                created_task_ids.append(task.id)
                self.tasks.add_event(
                    task.id,
                    TaskEventCreate(
                        event_type="daily_plan_created",
                        message="Task created by autonomous daily planning.",
                        metadata={
                            "project_slug": project.slug,
                            "base_agent": item.base_agent,
                            "profile_id": item.profile_id,
                            "profile_name": item.profile_name,
                        },
                    ),
                )
                if plan.fallback_used:
                    self.tasks.add_event(
                        task.id,
                        TaskEventCreate(
                            event_type="pmo_fallback_used",
                            message="PMO planner used deterministic fallback.",
                            metadata={"project_slug": project.slug},
                        ),
                    )

        if created_task_ids:
            summary_lines.append(f"Я уже создал задач: {len(created_task_ids)}. Посмотреть: /tasks")
        else:
            summary_lines.append("Новых задач не создал: есть открытые задачи для продолжения.")

        summary = "\n".join(summary_lines)
        if notify:
            await self.notifier(summary)
        return DailyPlanResponse(
            status="ok",
            summary=summary,
            created_task_ids=created_task_ids,
            project_slugs=[project.slug for project in projects],
        )

    async def poll_queued_tasks(self, *, notify: bool = True) -> dict[str, Any]:
        expired_approvals = self.approvals.expire_pending()
        stuck_result = self.tasks.detect_stuck_tasks()
        retried_failed = self.tasks.retry_failed_tasks()
        queued_tasks = self.tasks.list_tasks(status="queued")
        completed: list[int] = []
        waiting_approval: list[int] = []
        failed: list[int] = []

        for task in queued_tasks:
            try:
                result = self.tasks.run_task(task.id)
            except Exception as error:
                self.tasks.update_status(task.id, "failed", message=str(error))
                failed.append(task.id)
                continue
            if not result:
                failed.append(task.id)
                continue
            if result["status"] == "waiting_approval":
                waiting_approval.append(task.id)
                if notify:
                    message = (
                        "Approval required\n\n"
                        f"Project: {task.project.slug if task.project else 'none'}\n"
                        f"Task: #{task.id} {task.title}\n"
                        "Action: run_task\n"
                        "Risk: medium\n\n"
                        f"Approve: /approve {result['approval_id']}\n"
                        f"Reject: /reject {result['approval_id']}"
                    )
                    if self.notifier is send_telegram_message:
                        await send_telegram_approval_request(message, int(result["approval_id"]))
                    else:
                        await self.notifier(message)
            elif result["status"] == "completed":
                completed.append(task.id)
                if notify:
                    await self.notifier(f"Задача #{task.id} завершена: {task.title}")

        return {
            "status": "ok",
            "completed": completed,
            "waiting_approval": waiting_approval,
            "failed": failed,
            "expired_approvals": expired_approvals,
            "stuck_requeued": stuck_result["requeued"],
            "stuck": stuck_result["stuck"],
            "retried_failed": retried_failed,
        }

    async def evening_review(self, *, notify: bool = True) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        since = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        tasks = self.tasks.list_tasks_since(since)
        completed = [task for task in tasks if task.status == "completed"]
        waiting = [task for task in tasks if task.status == "waiting_approval"]
        failed = [task for task in tasks if task.status == "failed"]

        summary = (
            "Вечерний отчет AI Office\n"
            f"Обновлено задач сегодня: {len(tasks)}\n"
            f"Завершено: {len(completed)}\n"
            f"Ждет approval: {len(waiting)}\n"
            f"Ошибки: {len(failed)}"
        )
        self.memory.remember(
            content=summary,
            scope="personal",
            kind="summary",
            agent_id="pmo",
            metadata={"source": "evening_review"},
        )
        if notify:
            await self.notifier(summary)
        return {
            "status": "ok",
            "summary": summary,
            "completed": [task.id for task in completed],
            "waiting_approval": [task.id for task in waiting],
            "failed": [task.id for task in failed],
        }

    def task_needs_approval(self, task: Task) -> bool:
        return classify_task(
            task.title,
            task.description,
            requires_approval=task.requires_approval,
        ).requires_approval

    def ensure_project_from_goal(self, goal: str, project_slug: str | None = None) -> tuple[str, list[int]]:
        plan = self.planner.plan_from_text(goal=goal, project_slug=project_slug)
        project = self.projects.create_project(
            ProjectCreate(
                slug=plan.project_slug,
                name=plan.project_slug.replace("-", " ").title(),
                goal=plan.goal,
                priority=2,
            )
        )
        task_ids: list[int] = []
        for item in plan.tasks:
            task = self.tasks.create_task(
                TaskCreate(
                    project_id=project.id,
                    title=item.title,
                    description=item.description,
                    created_by="pmo",
                    assigned_agent=item.assigned_agent,
                    status="planned",
                    priority=item.priority,
                    requires_approval=item.requires_approval,
                    base_agent=item.base_agent,
                    profile_id=item.profile_id,
                    profile_name=item.profile_name,
                )
            )
            task_ids.append(task.id)
            if plan.fallback_used:
                self.tasks.add_event(
                    task.id,
                    TaskEventCreate(
                        event_type="pmo_fallback_used",
                        message="PMO planner used deterministic fallback.",
                    ),
                )
        return project.slug, task_ids
