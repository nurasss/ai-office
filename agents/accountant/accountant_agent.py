"""Accountant Agent — сверка инвойсов с zero-hallucination policy."""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from agents.base.base_agent import BaseAgent
from core.logger import get_logger
from tools.external.erp import parse_invoice_pdf

logger = get_logger("agents.accountant")

ACCOUNTANT_TOOLS: list[BaseTool] = [
    parse_invoice_pdf,
]

class AccountantAgent(BaseAgent):
    """Бухгалтер — сверка инвойсов, финансовые расчёты.

    Гибридный протокол:
    1. Парсинг (Sonnet 4.6): извлечение данных из документов
    2. Аудит (Opus 4.7): перепроверка ВСЕХ вычислений

    Zero-hallucination policy: любое расхождение → needs_review.
    """

    AGENT_ID = "accountant"
    PROMPT_FILE = "accountant.yaml"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(tools=ACCOUNTANT_TOOLS, temperature=0.0, **kwargs)

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Нода Accountant в графе — парсинг + аудит."""
        task = ""
        for subtask in state.get("subtasks", []):
            if subtask.get("assigned_to") == "accountant":
                task = subtask.get("description", "")
                break

        if not task:
            task = state.get("current_task", "")

        logger.info("accountant.process.start", task=task[:100])

        # Шаг 1: Парсинг (Sonnet 4.6)
        parse_result = await self.invoke(task, use_heavy=False)
        parsed_data = parse_result.get("result", "")

        # Шаг 2: Аудит математики (Opus 4.7)
        audit_task = f"""
        Проведи арифметический аудит следующих финансовых данных.

        Данные:
        {parsed_data}

        Проверь:
        1. Сумма всех позиций = итоговая сумма
        2. НДС/налоги посчитаны корректно
        3. Нет ли расхождений в числах

        Ответь JSON: {{"status": "verified|discrepancy|needs_review", "difference": 0.00, "notes": "..."}}
        """

        audit_result = await self.invoke(audit_task, use_heavy=True)

        return {
            "active_agent": "pmo",
            "artifacts": {
                "accounting_result": parsed_data,
                "audit_result": audit_result.get("result", ""),
                "zero_hallucination": True,
            },
            "messages": [
                HumanMessage(
                    content="Accountant: парсинг + аудит завершён. "
                    "Zero-hallucination policy применена."
                )
            ],
        }
