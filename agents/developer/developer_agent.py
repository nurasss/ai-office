"""Developer Agent — написание и ревью кода."""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from agents.base.base_agent import BaseAgent
from core.logger import get_logger
from tools.external.github import create_github_pr, read_github_repo

logger = get_logger("agents.developer")

DEVELOPER_TOOLS: list[BaseTool] = [
    read_github_repo,
    create_github_pr,
]

class DeveloperAgent(BaseAgent):
    """Разработчик — написание кода, ревью, архитектура.

    Использует claude-opus-4-7 для максимального качества кода.
    """

    AGENT_ID = "developer"
    PROMPT_FILE = "developer.yaml"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(tools=DEVELOPER_TOOLS, **kwargs)

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Нода Developer в графе — написание/ревью кода."""
        task = ""
        for subtask in state.get("subtasks", []):
            if subtask.get("assigned_to") == "developer":
                task = subtask.get("description", "")
                break

        if not task:
            task = state.get("current_task", "")

        logger.info("developer.process.start", task=task[:100])

        result = await self.invoke(task)

        return {
            "active_agent": "pmo",
            "artifacts": {
                "code_result": result.get("result", ""),
                "task_id": result.get("task_id", ""),
            },
            "messages": [
                HumanMessage(content="Developer: код написан/отревьюирован.")
            ],
        }
