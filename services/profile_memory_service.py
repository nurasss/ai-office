"""Persistent user/project memory helpers for the Telegram product bot."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Memory, UserProfile
from services.memory_service import MemoryService


class ProfileMemoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.memory = MemoryService(db)

    def ensure_profile(self, *, external_id: str, display_name: str = "") -> UserProfile:
        profile = self.db.scalar(select(UserProfile).where(UserProfile.external_id == external_id))
        if profile:
            if display_name and not profile.display_name:
                profile.display_name = display_name
                self.db.commit()
                self.db.refresh(profile)
            return profile
        profile = UserProfile(external_id=external_id, display_name=display_name)
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def remember_fact(
        self,
        *,
        external_id: str,
        text: str,
        display_name: str = "",
        project_slug: str | None = None,
    ) -> Memory:
        profile = self.ensure_profile(external_id=external_id, display_name=display_name)
        normalized = text.strip()
        lowered = normalized.lower()
        if "отвечай" in lowered or "стиль" in lowered:
            profile.communication_style = normalized
        if "главный проект" in lowered and project_slug:
            profile.primary_project_slug = project_slug
        preference_bucket = dict(profile.preferences_json or {})
        preference_bucket.setdefault("facts", [])
        preference_bucket["facts"] = [*preference_bucket["facts"], normalized][-20:]
        profile.preferences_json = preference_bucket
        self.db.add(profile)
        memory = self.memory.remember(
            content=normalized,
            scope="personal",
            kind=_classify_memory_kind(lowered),
            project_slug=project_slug,
            agent_id="memory",
            metadata={"external_id": external_id},
        )
        self.db.refresh(profile)
        return memory

    def memory_summary(self, *, external_id: str, project_slug: str | None = None) -> str:
        profile = self.ensure_profile(external_id=external_id)
        query = select(Memory).order_by(Memory.created_at.desc()).limit(40)
        memories = list(self.db.scalars(query))
        relevant = [
            memory for memory in memories
            if memory.metadata_json.get("external_id") == external_id
            or (project_slug and memory.project and memory.project.slug == project_slug)
        ]
        grouped: dict[str, list[str]] = defaultdict(list)
        for memory in relevant[:12]:
            grouped[memory.kind].append(memory.content)

        lines = [f"Память о пользователе: {profile.display_name or external_id}"]
        if profile.primary_project_slug:
            lines.append(f"Главный проект: {profile.primary_project_slug}")
        if profile.communication_style:
            lines.append(f"Стиль ответа: {profile.communication_style}")
        if not grouped:
            lines.append("Пока сохраненных фактов мало.")
            return "\n".join(lines)
        for kind, items in grouped.items():
            lines.append(f"{kind}:")
            lines.extend(f"- {item}" for item in items[:4])
        return "\n".join(lines)

    def project_summary(self, *, project_slug: str) -> str:
        memories = self.memory.latest_for_project(project_slug, limit=8)
        if not memories:
            return f"По проекту {project_slug} памяти пока нет."
        lines = [f"Что я знаю про {project_slug}:"]
        lines.extend(f"- {memory.content}" for memory in memories)
        return "\n".join(lines)


def _classify_memory_kind(lowered: str) -> str:
    if "проект" in lowered:
        return "project_memory"
    if "цель" in lowered or "инвест" in lowered:
        return "goal_memory"
    if "отвечай" in lowered or "стиль" in lowered:
        return "important_fact"
    return "important_fact"
