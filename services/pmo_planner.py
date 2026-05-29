"""Structured PMO planning with safe fallback routing."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from core.action_policy import classify_task
from core.schemas import PMOStructuredPlan, PMOTaskPlanItem
from services.agent_profile_registry import AgentProfileRegistry
from services.project_service import slugify


AGENT_KEYWORDS: list[tuple[str, str]] = [
    ("sql", "data_analyst"),
    ("данн", "data_analyst"),
    ("метрик", "data_analyst"),
    ("kpi", "data_analyst"),
    ("код", "developer"),
    ("api", "developer"),
    ("github", "developer"),
    ("тест", "developer"),
    ("deploy", "developer"),
    ("текст", "copywriter"),
    ("контент", "copywriter"),
    ("пост", "copywriter"),
    ("email", "copywriter"),
    ("поддерж", "support"),
    ("ошиб", "support"),
    ("баг", "support"),
    ("рынок", "strategist"),
    ("стратег", "strategist"),
    ("okr", "strategist"),
    ("инвойс", "accountant"),
    ("счет", "accountant"),
    ("счёт", "accountant"),
    ("налог", "accountant"),
]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


def infer_agent(task_text: str) -> str:
    text = task_text.lower()
    for keyword, agent_id in AGENT_KEYWORDS:
        if keyword in text:
            return agent_id
    return "developer" if any(word in text for word in ("build", "fix", "implement")) else "pmo"


class PMOPlanningService:
    """Build structured plans from goals, with no-key fallback behavior."""

    def __init__(self, registry: AgentProfileRegistry | None = None) -> None:
        self.registry = registry or AgentProfileRegistry()

    def plan_from_text(
        self,
        *,
        goal: str,
        project_slug: str | None = None,
        llm_text: str | None = None,
    ) -> PMOStructuredPlan:
        if llm_text:
            parsed = _extract_json_object(llm_text)
            if parsed:
                try:
                    plan = PMOStructuredPlan.model_validate(parsed)
                    return self._attach_profiles(plan)
                except ValidationError:
                    pass

        return self.fallback_plan(goal=goal, project_slug=project_slug)

    def fallback_plan(self, *, goal: str, project_slug: str | None = None) -> PMOStructuredPlan:
        title = _fallback_title(goal)
        agent_id = infer_agent(goal)
        policy = classify_task(title, goal)
        plan = PMOStructuredPlan(
            project_slug=slugify(project_slug or _infer_project_slug(goal)),
            goal=goal,
            fallback_used=True,
            tasks=[
                PMOTaskPlanItem(
                    title=title,
                    description=goal,
                    assigned_agent=agent_id,  # type: ignore[arg-type]
                    priority=2,
                    requires_approval=policy.requires_approval,
                )
            ],
        )
        return self._attach_profiles(plan)

    def _attach_profiles(self, plan: PMOStructuredPlan) -> PMOStructuredPlan:
        enriched_tasks: list[PMOTaskPlanItem] = []
        for task in plan.tasks:
            if task.profile_id and task.profile_name:
                enriched_tasks.append(task)
                continue
            try:
                profile = self.registry.select_profile_for_task(
                    f"{task.title}\n{task.description}",
                    base_agent=task.assigned_agent,
                )
            except Exception:
                profile = None
            if not profile:
                enriched_tasks.append(task)
                continue
            enriched_tasks.append(
                task.model_copy(
                    update={
                        "base_agent": profile.base_agent,
                        "profile_id": profile.id,
                        "profile_name": profile.name,
                    }
                )
            )
        return plan.model_copy(update={"tasks": enriched_tasks})


def _fallback_title(goal: str) -> str:
    compact = " ".join(goal.strip().split())
    if not compact:
        return "Clarify next project step"
    if len(compact) <= 90:
        return compact
    return f"{compact[:87].rstrip()}..."


def _infer_project_slug(goal: str) -> str:
    text = goal.lower()
    known = {
        "ai office": "ai-office",
        "ai-office": "ai-office",
        "nurapay": "nurapay",
        "apipay": "apipay",
        "stolab": "stolab",
        "sugardorama": "sugardorama",
    }
    for marker, slug in known.items():
        if marker in text:
            return slug
    return "ai-office"
