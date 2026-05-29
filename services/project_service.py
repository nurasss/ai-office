"""Project CRUD and seed helpers."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Project
from core.schemas import ProjectCreate, ProjectUpdate


def slugify(value: str) -> str:
    """Create a conservative URL/task-safe slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "project"


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_project(self, payload: ProjectCreate) -> Project:
        existing = self.get_project_by_slug(payload.slug)
        if existing:
            return existing

        project = Project(
            slug=slugify(payload.slug),
            name=payload.name,
            description=payload.description,
            goal=payload.goal,
            status=payload.status,
            priority=payload.priority,
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def upsert_project(self, payload: ProjectCreate) -> Project:
        project = self.get_project_by_slug(payload.slug)
        if not project:
            return self.create_project(payload)

        project.name = payload.name
        project.description = payload.description
        project.goal = payload.goal
        project.status = payload.status
        project.priority = payload.priority
        self.db.commit()
        self.db.refresh(project)
        return project

    def update_project(self, slug: str, payload: ProjectUpdate) -> Project | None:
        project = self.get_project_by_slug(slug)
        if not project:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(project, field, value)
        self.db.commit()
        self.db.refresh(project)
        return project

    def list_projects(self, status: str | None = None) -> list[Project]:
        query = select(Project).order_by(Project.priority.asc(), Project.updated_at.desc())
        if status:
            query = query.where(Project.status == status)
        return list(self.db.scalars(query))

    def get_project_by_slug(self, slug: str) -> Project | None:
        normalized = slugify(slug)
        return self.db.scalar(select(Project).where(Project.slug == normalized))

    def get_project(self, project_id: int) -> Project | None:
        return self.db.get(Project, project_id)

    def ensure_default_projects(self) -> list[Project]:
        """Create placeholder personal projects without private facts."""
        defaults = [
            ProjectCreate(
                slug="ai-office",
                name="AI Office",
                goal="Personal 24/7 AI office that safely moves active projects forward.",
                priority=1,
            ),
            ProjectCreate(slug="nurapay", name="NuraPay", goal="Maintain project memory and next actions.", priority=2),
            ProjectCreate(slug="apipay", name="ApiPay", goal="Maintain project memory and next actions.", priority=3),
            ProjectCreate(slug="stolab", name="stolab.kz", goal="Maintain project memory and next actions.", priority=3),
            ProjectCreate(slug="sugardorama", name="SugarDorama", goal="Maintain project memory and next actions.", priority=3),
        ]
        return [self.create_project(payload) for payload in defaults]

