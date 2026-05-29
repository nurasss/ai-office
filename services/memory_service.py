"""Practical project memory service backed by the SQL database."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Memory
from services.project_service import ProjectService


class MemoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def remember(
        self,
        *,
        content: str,
        scope: str = "personal",
        kind: str = "fact",
        project_slug: str | None = None,
        agent_id: str | None = None,
        metadata: dict | None = None,
    ) -> Memory:
        project_id = None
        if project_slug:
            project = ProjectService(self.db).get_project_by_slug(project_slug)
            project_id = project.id if project else None

        memory = Memory(
            scope=scope,
            project_id=project_id,
            agent_id=agent_id,
            kind=kind,
            content=content,
            metadata_json=metadata or {},
        )
        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def latest_for_project(self, project_slug: str, *, limit: int = 5) -> list[Memory]:
        project = ProjectService(self.db).get_project_by_slug(project_slug)
        if not project:
            return []
        query = (
            select(Memory)
            .where(Memory.project_id == project.id)
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(query))

    def latest_common(self, *, limit: int = 5) -> list[Memory]:
        query = (
            select(Memory)
            .where(Memory.scope.in_(["personal", "common"]))
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(query))

