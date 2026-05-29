"""PMO Agent — оркестратор, точка входа в граф."""

import json
from typing import Any, Sequence

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from agents.base.base_agent import BaseAgent
from core.logger import get_logger
from core.state import AgentRole, OfficeState, SubTask, TaskStatus
from services.pmo_planner import PMOPlanningService
from tools.external.github import read_github_repo
from tools.external.jira import search_jira_issues
from tools.external.slack import send_slack_message

logger = get_logger("agents.pmo")

# Инструменты PMO: чтение данных, коммуникация, но НЕ выполнение чужих задач
PMO_TOOLS: list[BaseTool] = [
    read_github_repo,
    search_jira_issues,
    send_slack_message,
]

class PMOAgent(BaseAgent):
    """Project Management Officer — оркестратор задач.

    Принимает запросы от CEO/пользователя, декомпозирует на подзадачи,
    маршрутизирует к нужным агентам через граф.
    """

    AGENT_ID = "pmo"
    PROMPT_FILE = "pmo.yaml"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(tools=PMO_TOOLS, **kwargs)

    async def plan_goal(self, goal: str, project_slug: str | None = None) -> dict[str, Any]:
        """Return a structured project/task plan, falling back safely without LLM."""
        planner = PMOPlanningService()
        prompt = (
            "Верни только JSON по схеме: "
            '{"project_slug":"ai-office","goal":"...","tasks":[{"title":"...",'
            '"description":"...","assigned_agent":"developer","priority":2,'
            '"requires_approval":false,"base_agent":"developer",'
            '"profile_id":"developer.backend_architect","profile_name":"Backend Architect"}]}.\n\n'
            f"Project slug hint: {project_slug or ''}\n"
            f"Goal:\n{goal}"
        )
        try:
            llm_text = await self.process_task(
                prompt,
                use_tools=False,
                max_tokens=1400,
            )
            return planner.plan_from_text(
                goal=goal,
                project_slug=project_slug,
                llm_text=llm_text,
            ).model_dump()
        except Exception as error:
            logger.warning("pmo.structured_plan.fallback", error=str(error))
            return planner.fallback_plan(goal=goal, project_slug=project_slug).model_dump()

    def _decompose_task(self, task: str) -> list[SubTask]:
        """Декомпозировать задачу на подзадачи через LLM.

        В продакшене — LLM вызов. Здесь — заглушка с маршрутизацией по ключевым словам.
        """
        task_lower = task.lower()
        subtasks: list[SubTask] = []

        # Простая эвристика маршрутизации (в продакшене — LLM-вызов)
        keyword_map: dict[str, AgentRole] = {
            "sql": AgentRole.DATA_ANALYST,
            "данные": AgentRole.DATA_ANALYST,
            "метрик": AgentRole.DATA_ANALYST,
            "kpi": AgentRole.DATA_ANALYST,
            "ltv": AgentRole.DATA_ANALYST,
            "cac": AgentRole.DATA_ANALYST,
            "дашборд": AgentRole.DATA_ANALYST,
            "анализ данных": AgentRole.DATA_ANALYST,
            "код": AgentRole.DEVELOPER,
            "программ": AgentRole.DEVELOPER,
            "разработ": AgentRole.DEVELOPER,
            "ревью": AgentRole.DEVELOPER,
            "pull request": AgentRole.DEVELOPER,
            "github": AgentRole.DEVELOPER,
            "api": AgentRole.DEVELOPER,
            "swagger": AgentRole.DEVELOPER,
            "текст": AgentRole.COPYWRITER,
            "контент": AgentRole.COPYWRITER,
            "стать": AgentRole.COPYWRITER,
            "пост": AgentRole.COPYWRITER,
            "email": AgentRole.COPYWRITER,
            "рассыл": AgentRole.COPYWRITER,
            "пресс-релиз": AgentRole.COPYWRITER,
            "поддержк": AgentRole.SUPPORT,
            "проблем": AgentRole.SUPPORT,
            "ошибк": AgentRole.SUPPORT,
            "баг": AgentRole.SUPPORT,
            "тикет": AgentRole.SUPPORT,
            "faq": AgentRole.SUPPORT,
            "инцидент": AgentRole.SUPPORT,
            "рынок": AgentRole.STRATEGIST,
            "стратеги": AgentRole.STRATEGIST,
            "конкурент": AgentRole.STRATEGIST,
            "swot": AgentRole.STRATEGIST,
            "pestel": AgentRole.STRATEGIST,
            "okr": AgentRole.STRATEGIST,
            "бизнес-план": AgentRole.STRATEGIST,
            "инвойс": AgentRole.ACCOUNTANT,
            "счёт": AgentRole.ACCOUNTANT,
            "счет": AgentRole.ACCOUNTANT,
            "финанс": AgentRole.ACCOUNTANT,
            "сверк": AgentRole.ACCOUNTANT,
            "акт": AgentRole.ACCOUNTANT,
            "ндс": AgentRole.ACCOUNTANT,
            "налог": AgentRole.ACCOUNTANT,
            "договор": AgentRole.ACCOUNTANT,
        }

        assigned_role = AgentRole.DATA_ANALYST  # fallback
        for keyword, role in keyword_map.items():
            if keyword in task_lower:
                assigned_role = role
                break

        subtasks.append({
            "task_id": f"subtask_{assigned_role.value}_001",
            "description": task,
            "assigned_to": assigned_role,
            "status": TaskStatus.PENDING,
            "result": "",
            "priority": 1,
            "depends_on": [],
        })

        logger.info(
            "pmo.decomposed",
            task=task[:100],
            subtasks_count=len(subtasks),
            assigned_to=assigned_role.value,
        )

        return subtasks

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Нода PMO в графе — декомпозиция + маршрутизация."""
        task = state.get("current_task", "")
        messages = state.get("messages", [])

        logger.info("pmo.process.start", task=task[:100])

        # Декомпозиция
        subtasks = self._decompose_task(task)

        # Определяем следующего агента
        next_agent = subtasks[0]["assigned_to"] if subtasks else AgentRole.DATA_ANALYST

        return {
            "subtasks": subtasks,
            "active_agent": next_agent.value,
            "messages": [
                HumanMessage(content=f"PMO: задача декомпозирована, маршрутизация → {next_agent.value}")
            ],
        }
