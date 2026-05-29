"""Lightweight runtime events for the pixel office UI."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

AGENT_IDS = (
    "pmo",
    "data_analyst",
    "developer",
    "copywriter",
    "support",
    "strategist",
    "accountant",
)

AGENT_NAMES = {
    "pmo": "PMO",
    "data_analyst": "Аналитик",
    "developer": "Разработчик",
    "copywriter": "Копирайтер",
    "support": "Поддержка",
    "strategist": "Стратег",
    "accountant": "Бухгалтер",
}

IDLE_STATUS = "idle"

_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
_agent_statuses: dict[str, dict[str, Any]] = {
    agent_id: {
        "type": "agent_status",
        "agent_id": agent_id,
        "agent_name": AGENT_NAMES.get(agent_id, agent_id),
        "status": IDLE_STATUS,
        "message": "Свободен",
        "task_id": "",
        "updated_at": time.time(),
    }
    for agent_id in AGENT_IDS
}


def get_agent_statuses() -> list[dict[str, Any]]:
    """Return the last known runtime status for each agent."""
    return [_agent_statuses[agent_id].copy() for agent_id in AGENT_IDS]


async def publish_agent_status(
    agent_id: str,
    status: str,
    *,
    message: str = "",
    task_id: str = "",
    handled_by: str = "",
    conversation_id: str = "",
) -> dict[str, Any]:
    """Publish an agent status event to live subscribers."""
    normalized_agent_id = agent_id if agent_id in AGENT_NAMES else "pmo"
    event = {
        "type": "agent_status",
        "agent_id": normalized_agent_id,
        "agent_name": AGENT_NAMES.get(normalized_agent_id, normalized_agent_id),
        "status": status,
        "message": message,
        "task_id": task_id,
        "handled_by": handled_by,
        "conversation_id": conversation_id,
        "updated_at": time.time(),
    }
    _agent_statuses[normalized_agent_id] = event.copy()

    dead_subscribers: list[asyncio.Queue[dict[str, Any]]] = []
    for queue in _subscribers:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            dead_subscribers.append(queue)

    for queue in dead_subscribers:
        _subscribers.discard(queue)

    return event


async def subscribe_agent_events() -> AsyncIterator[dict[str, Any]]:
    """Yield a snapshot and then live status events for SSE clients."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
    _subscribers.add(queue)
    try:
        yield {
            "type": "snapshot",
            "agents": get_agent_statuses(),
            "updated_at": time.time(),
        }
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                yield event
            except TimeoutError:
                yield {"type": "ping", "updated_at": time.time()}
    finally:
        _subscribers.discard(queue)


def format_sse(event: dict[str, Any]) -> str:
    """Serialize an event as a Server-Sent Events frame."""
    payload = json.dumps(event, ensure_ascii=False)
    return f"data: {payload}\n\n"


async def reset_agent_status_later(
    agent_id: str,
    *,
    delay_seconds: float = 2.5,
    task_id: str = "",
) -> None:
    """Return an agent to idle after the UI has had time to show completion."""
    with suppress(asyncio.CancelledError):
        await asyncio.sleep(delay_seconds)
        current_status = _agent_statuses.get(agent_id, {})
        if task_id and current_status.get("task_id") != task_id:
            return
        await publish_agent_status(agent_id, IDLE_STATUS, message="Свободен")
