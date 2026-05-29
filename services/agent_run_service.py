"""Agent run persistence helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import AgentRun, utc_now


class AgentRunService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_run(
        self,
        *,
        agent_id: str,
        task_id: int | None = None,
        input_payload: dict[str, Any] | None = None,
        status: str = "queued",
    ) -> AgentRun:
        run = AgentRun(
            task_id=task_id,
            agent_id=agent_id,
            status=status,
            input=input_payload or {},
            started_at=utc_now() if status == "running" else None,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def complete_run(self, run_id: int, output: dict[str, Any]) -> AgentRun | None:
        run = self.db.get(AgentRun, run_id)
        if not run:
            return None
        run.status = "completed"
        run.output = output
        run.completed_at = utc_now()
        self.db.commit()
        self.db.refresh(run)
        return run

    def fail_run(self, run_id: int, error: str) -> AgentRun | None:
        run = self.db.get(AgentRun, run_id)
        if not run:
            return None
        run.status = "failed"
        run.error = error
        run.completed_at = utc_now()
        self.db.commit()
        self.db.refresh(run)
        return run

    def list_runs(self, task_id: int | None = None) -> list[AgentRun]:
        query = select(AgentRun).order_by(AgentRun.created_at.desc())
        if task_id is not None:
            query = query.where(AgentRun.task_id == task_id)
        return list(self.db.scalars(query))

