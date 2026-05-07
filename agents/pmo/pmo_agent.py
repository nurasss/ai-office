"""PMO Agent — оркестратор, точка входа в граф."""

import json
from typing import Any, Sequence

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from agents.base.base_agent import BaseAgent
from core.logger import get_logger
from core.state import AgentRole, OfficeState, SubTask, TaskStatus
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
            "анализ данных": AgentRole.DATA_ANALYST,
            "код": AgentRole.DEVELOPER,
            "программ": AgentRole.DEVELOPER,
            "разработ": AgentRole.DEVELOPER,
            "ревью": AgentRole.DEVELOPER,
            "текст": AgentRole.COPYWRITER,
            "контент": AgentRole.COPYWRITER,
            "стать": AgentRole.COPYWRITER,
            "пост": AgentRole.COPYWRITER,
            "поддержк": AgentRole.SUPPORT,
            "проблем": AgentRole.SUPPORT,
            "ошибк": AgentRole.SUPPORT,
            "баг": AgentRole.SUPPORT,
            "рынок": AgentRole.STRATEGIST,
            "стратеги": AgentRole.STRATEGIST,
            "конкурент": AgentRole.STRATEGIST,
            "инвойс": AgentRole.ACCOUNTANT,
            "счёт": AgentRole.ACCOUNTANT,
            "финанс": AgentRole.ACCOUNTANT,
            "сверк": AgentRole.ACCOUNTANT,
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
