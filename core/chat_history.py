"""Persistent chat history for the web UI."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CHAT_HISTORY_DIR = Path(__file__).resolve().parent.parent / "data" / "chat_history"


def utc_now_iso() -> str:
    """Return an ISO timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


def build_chat_title(message: str) -> str:
    """Create a compact title from the first user prompt."""
    normalized = " ".join(message.strip().split())
    if not normalized:
        return "Новый диалог"
    if len(normalized) <= 48:
        return normalized
    return f"{normalized[:45].rstrip()}..."


@dataclass
class ChatMessage:
    """Single stored chat message."""

    role: str
    text: str
    created_at: str
    agent_id: str | None = None
    handled_by: str | None = None
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the message."""
        return {
            "role": self.role,
            "text": self.text,
            "created_at": self.created_at,
            "agent_id": self.agent_id,
            "handled_by": self.handled_by,
            "task_id": self.task_id,
        }


class ChatHistoryStore:
    """Simple JSON-backed conversation storage."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = self._resolve_storage_dir(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_storage_dir(self, base_dir: Path | None) -> Path:
        """Use the requested directory when writable, otherwise fall back to tmp."""
        candidate = Path(base_dir) if base_dir else CHAT_HISTORY_DIR
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(probe)
            return candidate
        except OSError:
            fallback = Path(tempfile.gettempdir()) / "ai-office" / "chat_history"
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def list_conversations(self) -> list[dict[str, Any]]:
        """Return lightweight metadata for all conversations."""
        conversations: list[dict[str, Any]] = []
        for path in self.base_dir.glob("*.json"):
            conversation = self._read_file(path)
            if not conversation:
                continue
            messages = conversation.get("messages", [])
            preview = ""
            if messages:
                preview = str(messages[-1].get("text", "")).strip().replace("\n", " ")
            conversations.append({
                "id": conversation.get("id", path.stem),
                "title": conversation.get("title", "Новый диалог"),
                "agent_id": conversation.get("agent_id", "pmo"),
                "created_at": conversation.get("created_at"),
                "updated_at": conversation.get("updated_at"),
                "message_count": len(messages),
                "preview": preview[:120],
            })

        conversations.sort(
            key=lambda item: item.get("updated_at") or item.get("created_at") or "",
            reverse=True,
        )
        return conversations

    def create_conversation(
        self,
        *,
        agent_id: str = "pmo",
        title: str = "Новый диалог",
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Create and persist an empty conversation."""
        conversation_id = conversation_id or uuid.uuid4().hex
        now = utc_now_iso()
        conversation = {
            "id": conversation_id,
            "title": title,
            "agent_id": agent_id,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self._write_file(conversation_id, conversation)
        return conversation

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        """Load a conversation by id."""
        return self._read_file(self._path_for(conversation_id))

    def touch_conversation(
        self,
        conversation_id: str,
        *,
        agent_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Update top-level metadata without changing messages."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise FileNotFoundError(conversation_id)
        if agent_id:
            conversation["agent_id"] = agent_id
        if title:
            conversation["title"] = title
        conversation["updated_at"] = utc_now_iso()
        self._write_file(conversation_id, conversation)
        return conversation

    def append_message(self, conversation_id: str, message: ChatMessage) -> dict[str, Any]:
        """Append a message to a conversation."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            raise FileNotFoundError(conversation_id)

        messages = conversation.setdefault("messages", [])
        messages.append(message.to_dict())
        if len(messages) == 1 and message.role == "user":
            conversation["title"] = build_chat_title(message.text)
        conversation["updated_at"] = message.created_at
        self._write_file(conversation_id, conversation)
        return conversation

    def recent_context(
        self,
        conversation_id: str,
        *,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """Return recent messages for prompt context."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return []
        return list(conversation.get("messages", []))[-limit:]

    def _path_for(self, conversation_id: str) -> Path:
        return self.base_dir / f"{conversation_id}.json"

    def _read_file(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_file(self, conversation_id: str, payload: dict[str, Any]) -> None:
        path = self._path_for(conversation_id)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
