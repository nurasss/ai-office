"""PMO Agent — оркестратор, точка входа в граф."""

import json
import re
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


ROUTING_PATTERNS: dict[AgentRole, tuple[str, ...]] = {
    AgentRole.STRATEGIST: (
        r"\bmarket\b",
        r"\bcompetitor",
        r"\bstrategy\b",
        r"\bswot\b",
        r"\bpestel\b",
        r"\bokr\b",
        r"\bnews\b",
        r"\bfintech\b",
        r"рын(ок|ка|ке|ку|ком)",
        r"новост",
        r"тренд",
        r"конкурент",
        r"стратег",
        r"бизнес[- ]?план",
        r"плат[её]ж",
        r"финтех",
        r"казахстан",
        r"последн(юю|ей|ие|их)",
        r"недел",
    ),
    AgentRole.DATA_ANALYST: (
        r"\bsql\b",
        r"\bkpi\b",
        r"\bltv\b",
        r"\bcac\b",
        r"\bcsv\b",
        r"данн",
        r"метрик",
        r"дашборд",
        r"аналити[кч]",
        r"отч[её]т",
        r"таблиц",
    ),
    AgentRole.DEVELOPER: (
        r"\bapi\b",
        r"\bgithub\b",
        r"\bswagger\b",
        r"\bpull request\b",
        r"код",
        r"программ",
        r"разработ",
        r"ревью",
        r"баг",
        r"депло",
    ),
    AgentRole.COPYWRITER: (
        r"\bemail\b",
        r"текст",
        r"контент",
        r"стат(ь|ья|ью|ьи)",
        r"пост",
        r"рассыл",
        r"пресс[- ]?релиз",
        r"копирайт",
    ),
    AgentRole.SUPPORT: (
        r"\bfaq\b",
        r"поддержк",
        r"проблем",
        r"ошибк",
        r"тикет",
        r"инцидент",
        r"клиентск",
    ),
    AgentRole.ACCOUNTANT: (
        r"инвойс",
        r"\bсч[её]т\b",
        r"\bсч[её]та\b",
        r"\bсч[её]ту\b",
        r"\bакт\b",
        r"\bакта\b",
        r"\bакту\b",
        r"\bндс\b",
        r"налог",
        r"договор",
        r"сверк",
        r"бухгалтер",
        r"первичн(ые|ая|ую|ых) документ",
    ),
}


def _route_task_by_rules(task: str) -> AgentRole:
    """Route by weighted keyword rules without matching short substrings."""
    normalized = task.lower().replace("ё", "е")
    scores: dict[AgentRole, int] = {role: 0 for role in ROUTING_PATTERNS}
    for role, patterns in ROUTING_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                scores[role] += 1

    # Market/news requests often contain finance words, but they need strategy/research.
    if scores[AgentRole.STRATEGIST] >= 2:
        return AgentRole.STRATEGIST

    best_role = max(scores, key=scores.get)
    return best_role if scores[best_role] > 0 else AgentRole.DATA_ANALYST


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
        subtasks: list[SubTask] = []
        assigned_role = _route_task_by_rules(task)

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
