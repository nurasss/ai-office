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
        self._use_database = base_dir is None
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
        if self._use_database:
            db_conversations = self._list_conversations_db()
            if db_conversations is not None:
                return db_conversations

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
        if self._use_database:
            conversation = self._create_conversation_db(
                conversation_id=conversation_id,
                agent_id=agent_id,
                title=title,
            )
            if conversation is not None:
                return conversation

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
        if self._use_database:
            conversation = self._get_conversation_db(conversation_id)
            if conversation is not None:
                return conversation
        return self._read_file(self._path_for(conversation_id))

    def touch_conversation(
        self,
        conversation_id: str,
        *,
        agent_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Update top-level metadata without changing messages."""
        if self._use_database:
            conversation = self._touch_conversation_db(
                conversation_id,
                agent_id=agent_id,
                title=title,
            )
            if conversation is not None:
                return conversation

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
        if self._use_database:
            conversation = self._append_message_db(conversation_id, message)
            if conversation is not None:
                return conversation

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
        if self._use_database:
            context = self._recent_context_db(conversation_id, limit=limit)
            if context is not None:
                return context

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

    def _list_conversations_db(self) -> list[dict[str, Any]] | None:
        try:
            from sqlalchemy import func, select

            from core.db import get_session, init_db, should_auto_create_tables
            from core.models import Conversation, Message

            if should_auto_create_tables():
                init_db()
            with get_session() as db:
                rows = db.execute(
                    select(
                        Conversation,
                        func.count(Message.id).label("message_count"),
                    )
                    .outerjoin(Message)
                    .group_by(Conversation.id)
                    .order_by(Conversation.updated_at.desc())
                ).all()
                return [
                    {
                        "id": conversation.external_id,
                        "title": conversation.title or "Новый диалог",
                        "agent_id": "pmo",
                        "created_at": conversation.created_at.isoformat(),
                        "updated_at": conversation.updated_at.isoformat(),
                        "message_count": int(message_count),
                        "preview": "",
                    }
                    for conversation, message_count in rows
                ]
        except Exception:
            return None

    def _create_conversation_db(
        self,
        *,
        conversation_id: str,
        agent_id: str,
        title: str,
    ) -> dict[str, Any] | None:
        try:
            from core.db import get_session, init_db, should_auto_create_tables
            from core.models import Conversation

            if should_auto_create_tables():
                init_db()
            with get_session() as db:
                existing = db.query(Conversation).filter_by(external_id=conversation_id).first()
                if existing:
                    return self._conversation_to_dict(existing, [])
                conversation = Conversation(
                    external_id=conversation_id,
                    source="telegram" if conversation_id.startswith("telegram_") else "web",
                    title=title,
                )
                db.add(conversation)
                db.commit()
                db.refresh(conversation)
                return self._conversation_to_dict(conversation, [])
        except Exception:
            return None

    def _get_conversation_db(self, conversation_id: str) -> dict[str, Any] | None:
        try:
            from sqlalchemy import select

            from core.db import get_session, init_db, should_auto_create_tables
            from core.models import Conversation, Message

            if should_auto_create_tables():
                init_db()
            with get_session() as db:
                conversation = db.query(Conversation).filter_by(external_id=conversation_id).first()
                if not conversation:
                    return None
                messages = list(
                    db.scalars(
                        select(Message)
                        .where(Message.conversation_id == conversation.id)
                        .order_by(Message.id.asc())
                    )
                )
                return self._conversation_to_dict(conversation, messages)
        except Exception:
            return None

    def _touch_conversation_db(
        self,
        conversation_id: str,
        *,
        agent_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            from core.db import get_session, init_db, should_auto_create_tables
            from core.models import Conversation, utc_now

            if should_auto_create_tables():
                init_db()
            with get_session() as db:
                conversation = db.query(Conversation).filter_by(external_id=conversation_id).first()
                if not conversation:
                    return None
                if title:
                    conversation.title = title
                conversation.updated_at = utc_now()
                db.commit()
                db.refresh(conversation)
                return self._conversation_to_dict(conversation, [])
        except Exception:
            return None

    def _append_message_db(
        self,
        conversation_id: str,
        message: ChatMessage,
    ) -> dict[str, Any] | None:
        try:
            from core.db import get_session, init_db, should_auto_create_tables
            from core.models import Conversation, Message, utc_now

            if should_auto_create_tables():
                init_db()
            with get_session() as db:
                conversation = db.query(Conversation).filter_by(external_id=conversation_id).first()
                if not conversation:
                    conversation = Conversation(
                        external_id=conversation_id,
                        source="telegram" if conversation_id.startswith("telegram_") else "web",
                        title="Новый диалог",
                    )
                    db.add(conversation)
                    db.flush()

                existing_count = (
                    db.query(Message)
                    .filter_by(conversation_id=conversation.id)
                    .count()
                )
                if existing_count == 0 and message.role == "user":
                    conversation.title = build_chat_title(message.text)

                db_message = Message(
                    conversation_id=conversation.id,
                    role=message.role,
                    agent_id=message.agent_id,
                    content=message.text,
                    metadata_json={
                        "handled_by": message.handled_by,
                        "task_id": message.task_id,
                    },
                )
                conversation.updated_at = utc_now()
                db.add(db_message)
                db.commit()
                messages = list(
                    db.query(Message)
                    .filter_by(conversation_id=conversation.id)
                    .order_by(Message.id.asc())
                )
                db.refresh(conversation)
                return self._conversation_to_dict(conversation, messages)
        except Exception:
            return None

    def _recent_context_db(
        self,
        conversation_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]] | None:
        try:
            from sqlalchemy import select

            from core.db import get_session, init_db, should_auto_create_tables
            from core.models import Conversation, Message

            if should_auto_create_tables():
                init_db()
            with get_session() as db:
                conversation = db.query(Conversation).filter_by(external_id=conversation_id).first()
                if not conversation:
                    return []
                messages = list(
                    db.scalars(
                        select(Message)
                        .where(Message.conversation_id == conversation.id)
                        .order_by(Message.id.desc())
                        .limit(limit)
                    )
                )
                messages.reverse()
                return [self._message_to_dict(message) for message in messages]
        except Exception:
            return None

    def _conversation_to_dict(self, conversation: Any, messages: list[Any]) -> dict[str, Any]:
        return {
            "id": conversation.external_id,
            "title": conversation.title or "Новый диалог",
            "agent_id": "pmo",
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
            "messages": [self._message_to_dict(message) for message in messages],
        }

    def _message_to_dict(self, message: Any) -> dict[str, Any]:
        metadata = message.metadata_json or {}
        return {
            "role": message.role,
            "text": message.content,
            "created_at": message.created_at.isoformat(),
            "agent_id": message.agent_id,
            "handled_by": metadata.get("handled_by"),
            "task_id": metadata.get("task_id"),
        }
