"""Small DB-backed queue facade used in local pilot mode."""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.models import Task
from services.audit_service import audit_log


def enqueue_task(db: Session, task_id: int) -> bool:
    task = db.get(Task, task_id)
    if not task:
        return False
    if task.status == "planned":
        task.status = "pending"
    audit_log(
        db,
        workspace_id=task.workspace_id or "default",
        task_id=task.id,
        actor_type="system",
        actor_id="queue",
        action="task.created",
        object_type="task",
        object_id=task.id,
        metadata={"status": task.status, "assigned_agent": task.assigned_agent},
    )
    db.commit()
    return True
