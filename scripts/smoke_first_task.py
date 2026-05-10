"""Offline smoke run for the first AI Office task.

The script verifies the full local loop that does not require API keys:

1. PMO routes the user task.
2. The agent-specific RAG namespaces return scoped context.
3. A deterministic draft is produced for inspection.

For live LLM execution, run the web app or orchestrator with real API keys.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.pmo.pmo_agent import PMOAgent
from rag.retriever import Retriever

DEFAULT_TASK = (
    "Привет, напиши короткий пост о том, что мы запустили ИИ-офис, "
    "и отправь мне черновик"
)


async def main() -> None:
    task = " ".join(sys.argv[1:]).strip() or DEFAULT_TASK

    pmo = PMOAgent()
    subtasks = pmo._decompose_task(task)
    assigned_to = subtasks[0]["assigned_to"].value

    pmo_context = await Retriever(agent_id="pmo").retrieve(task)
    agent_context = await Retriever(agent_id=assigned_to).retrieve(task)

    print("AI Office smoke run")
    print("=" * 64)
    print(f"Task: {task}")
    print(f"PMO route: pmo -> {assigned_to}")
    print()
    print_context("PMO RAG context", pmo_context)
    print_context(f"{assigned_to} RAG context", agent_context)

    if assigned_to == "copywriter":
        print("Draft from Copywriter_Agent (offline deterministic smoke):")
        print()
        print(
            "Мы запустили AI Office - внутренний цифровой офис из ИИ-сотрудников.\n\n"
            "Теперь типовые задачи можно передавать через PMO: система сама определит, "
            "кому поручить текст, аналитику, поддержку, код, стратегию или финансовую сверку.\n\n"
            "Главная цель пилота - ускорить первый результат и снять рутину с команды, "
            "оставив финальное решение за человеком."
        )
    else:
        print(f"Next agent to invoke in live mode: {assigned_to}")


def print_context(title: str, documents: list[dict]) -> None:
    print(f"{title}: {len(documents)} hit(s)")
    for document in documents:
        metadata = document.get("metadata", {})
        source = metadata.get("source", "unknown")
        namespace = metadata.get("namespace", "unknown")
        score = document.get("score", 0)
        print(f"- namespace={namespace} score={score} source={source}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
