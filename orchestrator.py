"""Главный оркестратор — LangGraph StateGraph.

PMO — входная нода (entry point). PMO декомпозирует задачу и
маршрутизирует к нужному агенту. Каждый агент — отдельный узел графа.
"""

from typing import Any

from langgraph.graph import END, StateGraph

from agents import (
    AccountantAgent,
    CopywriterAgent,
    DataAnalystAgent,
    DeveloperAgent,
    PMOAgent,
    StrategistAgent,
    SupportAgent,
)
from core.config import load_agent_config
from core.llm_router import LLMRouter
from core.logger import get_logger, setup_logging
from core.state import AgentRole, OfficeState

logger = get_logger("orchestrator")

def create_agent(role: str, router: LLMRouter) -> Any:
    """Фабрика агентов по роли."""
    registry = {
        AgentRole.PMO.value: PMOAgent,
        AgentRole.DATA_ANALYST.value: DataAnalystAgent,
        AgentRole.DEVELOPER.value: DeveloperAgent,
        AgentRole.COPYWRITER.value: CopywriterAgent,
        AgentRole.SUPPORT.value: SupportAgent,
        AgentRole.STRATEGIST.value: StrategistAgent,
        AgentRole.ACCOUNTANT.value: AccountantAgent,
    }
    agent_cls = registry.get(role)
    if not agent_cls:
        raise ValueError(f"Unknown agent role: {role}")
    return agent_cls(router=router)

def route_from_pmo(state: OfficeState) -> str:
    """Маршрутизация от PMO к нужному агенту."""
    active = state.get("active_agent", "")
    logger.info("router.from_pmo", active_agent=active)
    return active

def should_continue(state: OfficeState) -> str:
    """Проверить, нужно ли продолжать выполнение графа."""
    iterations = state.get("iterations", 0)
    config = load_agent_config().get("orchestrator", {})
    max_iterations = config.get("max_graph_iterations", 50)

    if iterations >= max_iterations:
        logger.warning("orchestrator.max_iterations", iterations=iterations)
        return "end"

    active = state.get("active_agent", "")
    if active == "pmo" and state.get("subtasks"):
        # Все подзадачи выполнены — возврат к PMO для финального ответа
        all_done = all(
            st.get("status") in ("completed", "failed")
            for st in state.get("subtasks", [])
        )
        if all_done:
            return "end"

    return "continue"

def build_graph() -> StateGraph:
    """Построить LangGraph StateGraph для ИИ-офиса.

    Структура:
        pmo → data_analyst → pmo → END
        pmo → developer → pmo → END
        pmo → copywriter → pmo → END
        pmo → support → pmo → END
        pmo → strategist → pmo → END
        pmo → accountant → pmo → END
    """
    setup_logging("INFO")
    router = LLMRouter()

    graph = StateGraph(OfficeState)

    # ── Создаём агентов ────────────────────────────────────────────────
    agents: dict[str, Any] = {}
    for role in AgentRole:
        agents[role.value] = create_agent(role.value, router)

    # ── Добавляем ноды ─────────────────────────────────────────────────
    for role_name, agent in agents.items():
        graph.add_node(role_name, agent.process)

    # ── Маршрутизация от PMO ────────────────────────────────────────────
    agent_roles = [r.value for r in AgentRole if r != AgentRole.PMO]
    graph.add_conditional_edges(
        AgentRole.PMO.value,
        route_from_pmo,
        {role: role for role in agent_roles},
    )

    # ── Каждый агент возвращает управление в PMO ───────────────────────
    for role in agent_roles:
        graph.add_edge(role, AgentRole.PMO.value)

    # ── PMO решает: продолжать или завершить ───────────────────────────
    graph.add_conditional_edges(
        AgentRole.PMO.value,
        should_continue,
        {
            "continue": AgentRole.PMO.value,
            "end": END,
        },
    )

    # ── Точка входа ────────────────────────────────────────────────────
    graph.set_entry_point(AgentRole.PMO.value)

    logger.info("orchestrator.graph.built", agents=list(agents.keys()))
    return graph

async def run(task: str) -> dict[str, Any]:
    """Запустить оркестратор с задачей.

    Args:
        task: задача от пользователя.

    Returns:
        Финальное состояние графа.
    """
    graph = build_graph()
    compiled = graph.compile()

    initial_state: OfficeState = {
        "messages": [],
        "current_task": task,
        "active_agent": "pmo",
        "subtasks": [],
        "artifacts": {},
        "context": {},
        "error": "",
        "iterations": 0,
    }

    config = load_agent_config().get("orchestrator", {})
    recursion_limit = config.get("recursion_limit", 100)

    logger.info("orchestrator.run.start", task=task[:100])
    result = await compiled.ainvoke(
        initial_state,
        config={"recursion_limit": recursion_limit},
    )
    logger.info("orchestrator.run.done")

    return result

if __name__ == "__main__":
    import asyncio

    asyncio.run(run("Проанализируй продажи за Q1 2026 и напиши отчёт"))
