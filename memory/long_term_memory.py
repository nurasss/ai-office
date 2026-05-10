"""File-backed long-term memory for agent successes and incidents.

The store is intentionally simple for the MVP: each agent gets an isolated
JSONL file under data/memory/. The data/ directory is git-ignored, so local
runtime memory does not leak into commits.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from core.config import load_agent_config
from core.logger import get_logger

logger = get_logger("memory.long_term")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MEMORY_PATH = PROJECT_ROOT / "data" / "memory"
MAX_TEXT_CHARS = 1200


@dataclass
class MemoryEvent:
    """One durable memory event for an agent."""

    agent_id: str
    event_type: str
    task: str
    lesson: str
    outcome: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:12]}")
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEvent":
        """Deserialize an event from JSONL."""
        return cls(
            agent_id=data["agent_id"],
            event_type=data["event_type"],
            task=data.get("task", ""),
            lesson=data.get("lesson", ""),
            outcome=data.get("outcome", ""),
            metadata=data.get("metadata", {}),
            event_id=data.get("event_id", f"mem_{uuid.uuid4().hex[:12]}"),
            created_at=data.get("created_at", ""),
        )


class LongTermMemoryStore:
    """JSONL memory store with per-agent isolation."""

    def __init__(self, storage_path: Path | None = None) -> None:
        config = load_agent_config().get("memory", {})
        configured_path = config.get("storage_path")
        self.storage_path = (
            Path(configured_path)
            if configured_path and storage_path is None
            else storage_path or DEFAULT_MEMORY_PATH
        )
        if not self.storage_path.is_absolute():
            self.storage_path = PROJECT_ROOT / self.storage_path

        self.enabled = config.get("enabled", True)
        self.max_events_per_context = config.get("max_events_per_context", 3)
        self.shared_incident_namespace = config.get(
            "shared_incident_namespace",
            "common_incidents",
        )
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def append(self, event: MemoryEvent) -> None:
        """Append a memory event to its agent-specific JSONL file."""
        if not self.enabled:
            return

        path = self._path_for(event.agent_id)
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

        logger.info(
            "memory.appended",
            agent_id=event.agent_id,
            event_type=event.event_type,
            event_id=event.event_id,
        )

    def record_success(
        self,
        *,
        agent_id: str,
        task: str,
        outcome: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a compact successful decision for future similar tasks."""
        self.append(
            MemoryEvent(
                agent_id=agent_id,
                event_type="success",
                task=_truncate(task),
                outcome=_truncate(outcome),
                lesson="Использовать как пример успешного решения похожей задачи.",
                metadata=metadata or {},
            )
        )

    def record_incident(
        self,
        *,
        agent_id: str,
        task: str,
        lesson: str,
        outcome: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a correction or incident, for example PMO misrouting feedback."""
        self.append(
            MemoryEvent(
                agent_id=agent_id,
                event_type="incident",
                task=_truncate(task),
                outcome=_truncate(outcome),
                lesson=_truncate(lesson),
                metadata=metadata or {},
            )
        )

    def search(
        self,
        *,
        agent_id: str,
        query: str,
        limit: int | None = None,
        include_common: bool = True,
    ) -> list[MemoryEvent]:
        """Return relevant memories using lightweight token overlap ranking."""
        if not self.enabled:
            return []

        limit = limit or self.max_events_per_context
        candidates = list(self._read_events(agent_id))

        if include_common and agent_id != self.shared_incident_namespace:
            candidates.extend(self._read_events(self.shared_incident_namespace))

        if not candidates:
            return []

        query_tokens = _tokens(query)
        ranked = sorted(
            candidates,
            key=lambda event: _score_event(event, query_tokens),
            reverse=True,
        )
        return [event for event in ranked if _score_event(event, query_tokens) > 0][
            :limit
        ]

    def _read_events(self, agent_id: str) -> Iterable[MemoryEvent]:
        path = self._path_for(agent_id)
        if not path.exists():
            return []

        events: list[MemoryEvent] = []
        with open(path, "r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    events.append(MemoryEvent.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError) as error:
                    logger.warning(
                        "memory.bad_event",
                        agent_id=agent_id,
                        error=str(error),
                    )
        return events

    def _path_for(self, agent_id: str) -> Path:
        safe_agent_id = re.sub(r"[^a-zA-Z0-9_-]", "_", agent_id)
        return self.storage_path / f"{safe_agent_id}.jsonl"


def format_memory_context(events: list[MemoryEvent]) -> str:
    """Render memories into a compact prompt block."""
    if not events:
        return ""

    lines = ["Долгосрочная память по похожим задачам:"]
    for event in events:
        lines.append(
            "- "
            f"[{event.event_type}] {event.lesson} "
            f"Задача: {event.task}. "
            f"Итог: {event.outcome}"
        )
    return "\n".join(lines)


def _truncate(text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    text = str(text).strip()
    return text if len(text) <= max_chars else f"{text[:max_chars]}..."


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_]{3,}", text.lower())
        if token
    }


def _score_event(event: MemoryEvent, query_tokens: set[str]) -> int:
    event_tokens = _tokens(" ".join([event.task, event.lesson, event.outcome]))
    return len(query_tokens.intersection(event_tokens))
