"""Live smoke run for the first AI Office task.

The script verifies the local loop and then calls the routed agent's real LLM:

1. PMO routes the user task.
2. The agent-specific RAG namespaces return scoped context.
3. The routed agent receives system prompt + RAG context + task.

Use --route-only when you want to inspect routing/RAG without spending tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents import (
    AccountantAgent,
    CopywriterAgent,
    DataAnalystAgent,
    DeveloperAgent,
    PMOAgent,
    StrategistAgent,
    SupportAgent,
)
from agents.base.base_agent import BaseAgent
from core.llm_router import MissingLLMCredentialsError
from rag.retriever import Retriever

DEFAULT_TASK = (
    "Привет, напиши короткий пост о том, что мы запустили ИИ-офис, "
    "и отправь мне черновик"
)

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "accountant": AccountantAgent,
    "copywriter": CopywriterAgent,
    "data_analyst": DataAnalystAgent,
    "developer": DeveloperAgent,
    "strategist": StrategistAgent,
    "support": SupportAgent,
}


async def main() -> None:
    args = parse_args()
    task = args.task or DEFAULT_TASK

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

    if args.route_only:
        print(f"Route-only mode: next live agent would be {assigned_to}")
        return

    agent = create_agent(assigned_to)
    rag_text = "\n\n".join(
        str(document.get("content", "")).strip()
        for document in agent_context
        if str(document.get("content", "")).strip()
    )

    try:
        final_result = await agent.process_task(task, rag_context=rag_text)
    except MissingLLMCredentialsError as error:
        print("Live LLM call was not started.")
        print(str(error))
        raise SystemExit(2) from error

    print("--- РЕАЛЬНЫЙ ОТВЕТ ОТ LLM ---")
    print(final_result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the first live AI Office task.")
    parser.add_argument(
        "task",
        nargs="*",
        help="Task text. Defaults to the AI Office launch post request.",
    )
    parser.add_argument(
        "--route-only",
        action="store_true",
        help="Only print PMO route and RAG hits; do not call the LLM.",
    )
    args = parser.parse_args()
    args.task = " ".join(args.task).strip()
    return args


def create_agent(agent_id: str) -> BaseAgent:
    agent_cls = AGENT_REGISTRY.get(agent_id)
    if not agent_cls:
        raise ValueError(f"Smoke script cannot create agent: {agent_id}")
    return agent_cls()


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
