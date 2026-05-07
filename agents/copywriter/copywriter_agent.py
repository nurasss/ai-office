"""Copywriter Agent — создание контента."""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from agents.base.base_agent import BaseAgent
from core.logger import get_logger
from tools.external.slack import send_slack_message

logger = get_logger("agents.copywriter")

COPYWRITER_TOOLS: list[BaseTool] = [
    send_slack_message,
]

class CopywriterAgent(BaseAgent):
    """Копирайтер — тексты, статьи, email, контент-маркетинг."""

    AGENT_ID = "copywriter"
    PROMPT_FILE = "copywriter.yaml"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(tools=COPYWRITER_TOOLS, temperature=0.3, **kwargs)

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Нода Copywriter в графе — создание контента."""
        task = ""
        for subtask in state.get("subtasks", []):
            if subtask.get("assigned_to") == "copywriter":
                task = subtask.get("description", "")
                break

        if not task:
            task = state.get("current_task", "")

        logger.info("copywriter.process.start", task=task[:100])

        result = await self.invoke(task)

        return {
            "active_agent": "pmo",
            "artifacts": {
                "content_result": result.get("result", ""),
                "task_id": result.get("task_id", ""),
            },
            "messages": [
                HumanMessage(content="Copywriter: контент создан.")
            ],
        }
