"""Минимальный учебный пример LangGraph для AI Office.

Запуск:
    python office.py
"""

import operator
from typing import Annotated, List, TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph


load_dotenv()


class OfficeState(TypedDict, total=False):
    """Общая папка состояния, которую видят все узлы графа."""

    messages: Annotated[List[str], operator.add]
    task: str
    draft: str
    quality_score: int
    next_node: str


llm = ChatOpenAI(model="gpt-5.4", temperature=0)


def pmo_node(state: OfficeState) -> OfficeState:
    """PMO решает, кому передать задачу и принимать ли результат."""
    print("--- PMO ПРИНИМАЕТ РЕШЕНИЕ ---")

    if not state.get("draft"):
        return {
            "next_node": "copywriter",
            "messages": ["PMO: Начинаем работу над текстом."],
        }

    if state.get("quality_score", 0) < 70:
        return {
            "next_node": "copywriter",
            "messages": ["PMO: Качество низкое, переделай."],
        }

    return {
        "next_node": "end",
        "messages": ["PMO: Работа принята!"],
    }


def copywriter_node(state: OfficeState) -> OfficeState:
    """Копирайтер готовит черновик текста."""
    print("--- КОПИРАЙТЕР ПИШЕТ ТЕКСТ ---")
    response = llm.invoke(f"Напиши текст на тему: {state['task']}")

    return {
        "draft": response.content,
        "quality_score": state.get("quality_score", 85),
        "messages": ["Копирайтер: Текст готов."],
    }


workflow = StateGraph(OfficeState)
workflow.add_node("pmo", pmo_node)
workflow.add_node("copywriter", copywriter_node)
workflow.set_entry_point("pmo")

workflow.add_conditional_edges(
    "pmo",
    lambda state: state["next_node"],
    {
        "copywriter": "copywriter",
        "end": END,
    },
)
workflow.add_edge("copywriter", "pmo")

app = workflow.compile()


if __name__ == "__main__":
    inputs: OfficeState = {
        "task": "Напиши приветствие для нового ИИ-сотрудника",
        "messages": [],
        "quality_score": 85,
    }

    for output in app.stream(inputs, config={"recursion_limit": 10}):
        print(output)
