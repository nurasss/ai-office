"""Support Agent — техподдержка с каскадной эскалацией L1 → L2."""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from agents.base.base_agent import BaseAgent
from core.logger import get_logger
from tools.external.slack import send_slack_message

logger = get_logger("agents.support")

SUPPORT_TOOLS: list[BaseTool] = [
    send_slack_message,
]

class SupportAgent(BaseAgent):
    """Техподдержка — каскадная логика L1 (Sonnet) → L2 (Opus).

    L1: базовые вопросы, FAQ, известные решения.
    L2: сложные проблемы, отладка (эскалация при confidence < threshold).
    """

    AGENT_ID = "support"
    PROMPT_FILE = "support.yaml"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(tools=SUPPORT_TOOLS, **kwargs)

    def _should_escalate(self, confidence: float) -> bool:
        """Определить, нужна ли эскалация на L2."""
        threshold = self.config.get("escalation_threshold", 0.7)
        return confidence < threshold

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Нода Support в графе — L1 ответ с возможной эскалацией на L2."""
        task = ""
        for subtask in state.get("subtasks", []):
            if subtask.get("assigned_to") == "support":
                task = subtask.get("description", "")
                break

        if not task:
            task = state.get("current_task", "")

        logger.info("support.process.start", task=task[:100])

        # L1 ответ (Sonnet 4.6)
        l1_result = await self.invoke(task, use_heavy=False)

        # Оценка уверенности (в продакшене — из ответа L1)
        confidence = 0.5  # заглушка: средняя уверенность → эскалация

        if self._should_escalate(confidence):
            logger.info("support.escalation.l1_to_l2", confidence=confidence)

            # L2 эскалация (Opus 4.7)
            l2_result = await self.invoke(
                task,
                context={"l1_response": l1_result.get("result", "")},
                use_heavy=True,
            )

            return {
                "active_agent": "pmo",
                "artifacts": {
                    "support_result": l2_result.get("result", ""),
                    "escalated": True,
                    "l1_confidence": confidence,
                },
                "messages": [
                    HumanMessage(
                        content=f"Support (L2): эскалация выполнена. "
                        f"L1 confidence был {confidence}"
                    )
                ],
            }

        return {
            "active_agent": "pmo",
            "artifacts": {
                "support_result": l1_result.get("result", ""),
                "escalated": False,
                "confidence": confidence,
            },
            "messages": [
                HumanMessage(content=f"Support (L1): ответ дан. Confidence: {confidence}")
            ],
        }
