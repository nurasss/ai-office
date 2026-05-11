"""Product API for submitting tasks to the AI Office."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents import (
    AccountantAgent,
    BaseAgent,
    CopywriterAgent,
    DataAnalystAgent,
    DeveloperAgent,
    PMOAgent,
    StrategistAgent,
    SupportAgent,
)
from core.llm_router import MissingLLMCredentialsError
from core.logger import get_logger
from rag.retriever import Retriever
from tools.external.telegram import send_telegram_message

logger = get_logger("api.office")
router = APIRouter(prefix="/api/office", tags=["office"])

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "pmo": PMOAgent,
    "data_analyst": DataAnalystAgent,
    "developer": DeveloperAgent,
    "copywriter": CopywriterAgent,
    "support": SupportAgent,
    "strategist": StrategistAgent,
    "accountant": AccountantAgent,
}

AGENT_NAMES = {
    "pmo": "PMO",
    "data_analyst": "Аналитик",
    "developer": "Разработчик",
    "copywriter": "Копирайтер",
    "support": "Поддержка",
    "strategist": "Стратег",
    "accountant": "Бухгалтер",
}

_agents: dict[str, BaseAgent] = {}


class OfficeTaskRequest(BaseModel):
    """Request body for the product task endpoint."""

    task: str = Field(min_length=1, description="User task for the AI Office.")
    agent_id: str = Field(
        default="pmo",
        description="Agent id to call directly, or pmo for routing.",
    )
    route_only: bool = Field(
        default=False,
        description="Return PMO route and RAG hits without calling the LLM.",
    )
    notify_telegram: bool = Field(
        default=False,
        description="Send the final answer to Telegram if TELEGRAM_* env vars exist.",
    )


class OfficeRouteRequest(BaseModel):
    """Request body for route inspection."""

    task: str = Field(min_length=1, description="User task to route through PMO.")


class RagHit(BaseModel):
    """Compact RAG hit metadata for API clients."""

    namespace: str
    source: str
    score: int | float = 0


class OfficeTaskResponse(BaseModel):
    """Stable product response for web, Telegram, or Mini App clients."""

    status: str
    task_id: str
    requested_agent: str
    handled_by: str
    handled_by_name: str
    result: str = ""
    route: dict[str, Any] = Field(default_factory=dict)
    rag_hits: list[RagHit] = Field(default_factory=list)
    telegram_notified: bool = False


def get_agent(agent_id: str) -> BaseAgent:
    """Lazily instantiate a known agent."""
    agent_cls = AGENT_REGISTRY.get(agent_id)
    if not agent_cls:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")

    if agent_id not in _agents:
        _agents[agent_id] = agent_cls()
    return _agents[agent_id]


@router.post("/routes")
async def route_office_task(request: OfficeRouteRequest) -> dict[str, Any]:
    """Route a task through PMO without invoking the destination agent."""
    route = await route_with_pmo(request.task)
    return {
        "status": "ok",
        "task": request.task,
        **route,
    }


@router.post("/tasks", response_model=OfficeTaskResponse)
async def submit_office_task(request: OfficeTaskRequest) -> OfficeTaskResponse:
    """Submit a task to AI Office via PMO routing or direct agent execution."""
    requested_agent = request.agent_id.strip() or "pmo"
    if requested_agent not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {requested_agent}")

    route = (
        await route_with_pmo(request.task)
        if requested_agent == "pmo"
        else {"handled_by": requested_agent, "subtasks": []}
    )
    handled_by = route["handled_by"]
    rag_documents = await Retriever(agent_id=handled_by).retrieve(request.task)
    rag_hits = [to_rag_hit(document) for document in rag_documents]
    task_id = f"api_{uuid.uuid4().hex[:8]}"

    if request.route_only:
        return OfficeTaskResponse(
            status="routed",
            task_id=task_id,
            requested_agent=requested_agent,
            handled_by=handled_by,
            handled_by_name=AGENT_NAMES.get(handled_by, handled_by),
            route=route,
            rag_hits=rag_hits,
        )

    agent = get_agent(handled_by)
    rag_context = "\n\n".join(
        str(document.get("content", "")).strip()
        for document in rag_documents
        if str(document.get("content", "")).strip()
    )

    try:
        result = await agent.process_task(
            request.task,
            rag_context=rag_context,
            use_tools=False,
        )
    except MissingLLMCredentialsError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    telegram_notified = False
    if request.notify_telegram:
        telegram_notified = await notify_telegram(
            handled_by=handled_by,
            task=request.task,
            result=result,
            task_id=task_id,
        )

    return OfficeTaskResponse(
        status="ok",
        task_id=task_id,
        requested_agent=requested_agent,
        handled_by=handled_by,
        handled_by_name=AGENT_NAMES.get(handled_by, handled_by),
        result=result,
        route=route,
        rag_hits=rag_hits,
        telegram_notified=telegram_notified,
    )


async def route_with_pmo(task: str) -> dict[str, Any]:
    """Use PMO to pick the next agent and expose route metadata."""
    pmo = get_agent("pmo")
    route_result = await pmo.process({
        "current_task": task,
        "messages": [],
        "subtasks": [],
    })
    handled_by = route_result.get("active_agent", "data_analyst")
    if handled_by == "pmo":
        handled_by = "data_analyst"

    return {
        "handled_by": handled_by,
        "handled_by_name": AGENT_NAMES.get(handled_by, handled_by),
        "subtasks": route_result.get("subtasks", []),
    }


def to_rag_hit(document: dict[str, Any]) -> RagHit:
    """Convert a raw retriever document to compact API metadata."""
    metadata = document.get("metadata", {})
    return RagHit(
        namespace=str(metadata.get("namespace", "")),
        source=str(metadata.get("source") or metadata.get("source_id") or ""),
        score=document.get("score", 0),
    )


async def notify_telegram(
    *,
    handled_by: str,
    task: str,
    result: str,
    task_id: str,
) -> bool:
    """Send an optional Telegram notification for API clients."""
    return await send_telegram_message(
        "AI Office: задача завершена\n"
        f"Исполнитель: {AGENT_NAMES.get(handled_by, handled_by)}\n"
        f"Task ID: {task_id}\n"
        f"Запрос: {task[:700]}\n\n"
        f"Результат:\n{result[:1800]}"
    )
