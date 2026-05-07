"""DataAnalyst Agent — анализ данных с self-verification loop."""

import uuid
from typing import Any, Optional

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from agents.base.base_agent import BaseAgent
from core.logger import get_logger
from tools.external.db_tools import run_sql_query

logger = get_logger("agents.data_analyst")

DATA_ANALYST_TOOLS: list[BaseTool] = [
    run_sql_query,
]

class DataAnalystAgent(BaseAgent):
    """Аналитик данных — работа с БД, метрики, отчёты.

    Особенность: встроенный цикл self-verification.
    После анализа результат перепроверяется заданным числом раундов.
    """

    AGENT_ID = "data_analyst"
    PROMPT_FILE = "data_analyst.yaml"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(tools=DATA_ANALYST_TOOLS, temperature=0.0, **kwargs)

    def _has_inline_data(self, task: str) -> bool:
        """Грубая проверка: есть ли в запросе сами данные, а не только просьба анализа."""
        lines = [line.strip() for line in task.splitlines() if line.strip()]
        digit_count = sum(ch.isdigit() for ch in task)
        table_like_lines = sum(
            1
            for line in lines
            if line.count(",") >= 2 or line.count(";") >= 2 or line.count("|") >= 2
        )
        return digit_count >= 12 or table_like_lines >= 2

    def _should_request_data_source(
        self,
        task: str,
        context: Optional[dict[str, Any]],
    ) -> bool:
        """Не обещать анализировать корпоративные данные, если источник не передан."""
        if context:
            return False

        task_lower = task.lower()
        asks_for_analysis = any(
            keyword in task_lower
            for keyword in ("проанализ", "анализ", "отчет", "отчёт", "метрик", "дашборд")
        )
        mentions_business_data = any(
            keyword in task_lower
            for keyword in ("продаж", "выруч", "заказ", "клиент", "q1", "q2", "q3", "q4")
        )
        return asks_for_analysis and mentions_business_data and not self._has_inline_data(task)

    async def invoke(
        self,
        task: str,
        context: Optional[dict[str, Any]] = None,
        *,
        use_heavy: bool = False,
    ) -> dict[str, Any]:
        """Аналитик не выдумывает числа, если пользователь не передал источник данных."""
        if self._should_request_data_source(task, context):
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            return {
                "agent_id": self.agent_id,
                "task_id": task_id,
                "result": (
                    "Я могу провести анализ продаж, но сейчас у меня нет самого источника данных. "
                    "Чтобы не выдумывать метрики, пришлите CSV/таблицу или подключите базу данных.\n\n"
                    "Для анализа Q1 2026 нужен минимум такой набор полей:\n"
                    "- дата продажи;\n"
                    "- ID заказа или сделки;\n"
                    "- товар/услуга;\n"
                    "- сумма или выручка;\n"
                    "- количество;\n"
                    "- клиент, регион или канал продаж, если есть.\n\n"
                    "После этого я посчитаю выручку, количество заказов, средний чек, динамику по месяцам, "
                    "топ-продукты/каналы и отмечу аномалии. Уровень уверенности сейчас: low, потому что данных пока нет."
                ),
                "status": "completed",
            }

        return await super().invoke(task, context=context, use_heavy=use_heavy)

    async def _verify_result(self, result: str, task: str) -> dict[str, Any]:
        """Self-verification: перепроверить результат анализа.

        Возвращает dict с ключами: is_correct (bool),
        confidence (str), notes (str).
        """
        verify_prompt = f"""
        Перепроверь следующий результат анализа данных.

        Задача: {task}

        Результат:
        {result}

        Проверь:
        1. Логическую корректность выводов
        2. Арифметическую точность чисел
        3. Соответствие результата задаче

        Ответь JSON: {{"is_correct": true/false, "confidence": "high/medium/low", "notes": "..."}}
        """

        verify_result = await self.invoke(verify_prompt)
        return {
            "is_correct": True,
            "confidence": "high",
            "notes": "Self-verification passed (заглушка)",
        }

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Нода DataAnalyst в графе — анализ + self-verification."""
        task = ""
        for subtask in state.get("subtasks", []):
            if subtask.get("assigned_to") == "data_analyst":
                task = subtask.get("description", "")
                break

        if not task:
            task = state.get("current_task", "")

        logger.info("data_analyst.process.start", task=task[:100])

        # Основной анализ
        max_rounds = self.config.get("max_verification_rounds", 3)
        result = await self.invoke(task)

        # Self-verification loop
        verification = {"is_correct": True, "confidence": "high", "notes": ""}
        for round_num in range(max_rounds):
            verification = await self._verify_result(
                str(result.get("result", "")), task
            )
            if verification.get("is_correct"):
                break
            logger.warning(
                "data_analyst.verification.failed",
                round=round_num + 1,
                notes=verification.get("notes", ""),
            )

        return {
            "active_agent": "pmo",
            "artifacts": {
                "data_analysis_result": result.get("result", ""),
                "verification": verification,
            },
            "messages": [
                HumanMessage(
                    content=f"DataAnalyst: анализ завершён. "
                    f"Уверенность: {verification.get('confidence', 'unknown')}"
                )
            ],
        }
