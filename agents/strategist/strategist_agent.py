"""Strategist Agent — стратегический анализ, работа с большими документами."""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from agents.base.base_agent import BaseAgent
from core.logger import get_logger

logger = get_logger("agents.strategist")

STRATEGIST_TOOLS: list[BaseTool] = []  # RAG-поиск основной инструмент

class StrategistAgent(BaseAgent):
    """Стратег — анализ рынка, конкурентов, стратегические документы.

    Использует Gemini 3.1 Pro для работы с огромным контекстом (до 1M токенов).
    """

    AGENT_ID = "strategist"
    PROMPT_FILE = "strategist.yaml"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(tools=STRATEGIST_TOOLS, temperature=0.2, max_tokens=8192, **kwargs)

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Нода Strategist в графе — стратегический анализ."""
        task = ""
        for subtask in state.get("subtasks", []):
            if subtask.get("assigned_to") == "strategist":
                task = subtask.get("description", "")
                break

        if not task:
            task = state.get("current_task", "")

        logger.info("strategist.process.start", task=task[:100])

        result = await self.invoke(task)

        return {
            "active_agent": "pmo",
            "artifacts": {
                "strategy_result": result.get("result", ""),
                "task_id": result.get("task_id", ""),
            },
            "messages": [
                HumanMessage(content="Strategist: стратегический анализ завершён.")
            ],
        }
