"""Goal engine for Telegram-first autonomous planning."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Goal
from core.schemas import ProjectCreate, TaskCreate
from models.router import ModelRequest, PilotModelRouter
from services.audit_service import audit_log
from services.pmo_planner import PMOPlanningService
from services.project_service import ProjectService, slugify
from services.task_service import TaskService


class GoalEngineService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.planner = PMOPlanningService()
        self.projects = ProjectService(db)
        self.tasks = TaskService(db)

    def add_goal(
        self,
        *,
        external_id: str,
        title: str,
        workspace_id: str = "default",
    ) -> Goal:
        plan = self._plan_goal(title=title)
        goal = Goal(
            workspace_id=workspace_id,
            user_external_id=external_id,
            title=title,
            description=title,
            plan_json=[item.model_dump() for item in plan.tasks],
        )
        self.db.add(goal)
        self.db.commit()
        self.db.refresh(goal)
        audit_log(
            self.db,
            workspace_id=workspace_id,
            actor_type="user",
            actor_id=external_id,
            action="goal.created",
            object_type="goal",
            object_id=goal.id,
            metadata={"title": title},
            commit=True,
        )
        return goal

    def list_goals(self, *, external_id: str) -> list[Goal]:
        return list(
            self.db.scalars(
                select(Goal)
                .where(Goal.user_external_id == external_id)
                .order_by(Goal.updated_at.desc())
            )
        )

    def goal_status_text(self, *, external_id: str) -> str:
        goals = self.list_goals(external_id=external_id)
        if not goals:
            return "Активных целей пока нет. Добавьте через /add_goal."
        lines = ["Цели:"]
        for goal in goals[:8]:
            lines.append(
                f"#{goal.id} [{goal.status}] {'ON' if goal.autonomy_enabled else 'OFF'} {goal.title}"
            )
        return "\n".join(lines)

    def suggest_tasks_text(self, *, external_id: str) -> str:
        goals = [goal for goal in self.list_goals(external_id=external_id) if goal.status == "active"]
        if not goals:
            return "Пока нет активной цели. Добавьте ее через /add_goal."
        goal = goals[0]
        steps = goal.plan_json or []
        if not steps:
            return f"Для цели `{goal.title}` шаги пока не построены."
        lines = [f"По цели `{goal.title}` я предлагаю:"]
        for index, step in enumerate(steps[:6], start=1):
            lines.append(f"{index}. {step.get('title', 'Следующий шаг')}")
        return "\n".join(lines)

    def create_tasks_for_goal(self, *, goal_id: int, project_slug: str | None = None) -> list[int]:
        goal = self.db.get(Goal, goal_id)
        if not goal:
            return []
        target_slug = project_slug or slugify(goal.title)
        project = self.projects.create_project(
            ProjectCreate(
                slug=target_slug,
                name=target_slug.replace("-", " ").title(),
                goal=goal.title,
            )
        )
        return self._create_tasks_for_goal(goal=goal, project_slug=target_slug, project_id=project.id)

    def daily_plan_text(self, *, external_id: str) -> str:
        goals = [goal for goal in self.list_goals(external_id=external_id) if goal.status == "active"]
        if not goals:
            return "Доброе утро. Активных целей пока нет."
        goal = goals[0]
        lines = [f"Доброе утро. По цели `{goal.title}` я предлагаю сегодня:"]
        for index, step in enumerate((goal.plan_json or [])[:4], start=1):
            lines.append(f"{index}. {step.get('title', 'Следующий шаг')}")
        goal.last_daily_plan = "\n".join(lines)
        self.db.commit()
        return goal.last_daily_plan

    def set_autonomy(self, *, external_id: str, enabled: bool) -> str:
        goals = self.list_goals(external_id=external_id)
        for goal in goals:
            goal.autonomy_enabled = enabled
        self.db.commit()
        return "Автономный режим целей включен." if enabled else "Автономный режим целей выключен."

    def _plan_goal(self, *, title: str):
        project_slug = slugify(title)
        prompt = (
            "Верни только JSON по схеме: "
            '{"project_slug":"ai-office","goal":"...","tasks":[{"title":"...",'
            '"description":"...","assigned_agent":"developer","priority":2,'
            '"depends_on":[],"requires_approval":false,"base_agent":"developer",'
            '"profile_id":"developer.backend_architect","profile_name":"Backend Architect"}]}.\n\n'
            f"Goal:\n{title}"
        )
        try:
            _, response, _ = PilotModelRouter().generate(
                ModelRequest(
                    task_type="pmo",
                    risk_level="safe",
                    agent_name="pmo",
                    input_text=prompt,
                    requires_reasoning=True,
                )
            )
            return self.planner.plan_from_text(
                goal=title,
                project_slug=project_slug,
                llm_text=response.text,
            )
        except Exception:
            return self.planner.fallback_plan(goal=title, project_slug=project_slug)

    def _create_tasks_for_goal(self, *, goal: Goal, project_slug: str, project_id: int | None) -> list[int]:
        created_ids: list[int] = []
        for step in goal.plan_json[:6]:
            task = self.tasks.create_task(
                TaskCreate(
                    workspace_id=goal.workspace_id,
                    project_id=project_id,
                    title=step.get("title", goal.title),
                    description=step.get("description", goal.description),
                    input_text=step.get("description", goal.description),
                    created_by="pmo",
                    assigned_agent=step.get("assigned_agent", "pmo"),
                    status="pending",
                    priority=int(step.get("priority", 3)),
                    requires_approval=bool(step.get("requires_approval", False)),
                    risk_level="medium" if step.get("requires_approval") else "safe",
                )
            )
            created_ids.append(task.id)
        return created_ids
