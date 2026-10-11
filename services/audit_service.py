"""Append-only audit helpers for tasks, tools, approvals, and safety events."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import AuditEvent
from security.pii import redact_secrets_for_audit


def audit_log(
    db: Session,
    *,
    workspace_id: str | None = "default",
    actor_type: str = "system",
    actor_id: str = "",
    action: str,
    object_type: str = "",
    object_id: str | int = "",
    metadata: dict[str, Any] | None = None,
    task_id: int | None = None,
    commit: bool = False,
) -> AuditEvent:
    """Persist a redacted audit event.

    Callers may pass raw-ish operational metadata; this helper removes common
    secret/token patterns before the event is written.
    """
    event = AuditEvent(
        workspace_id=workspace_id,
        task_id=task_id,
        actor_type=actor_type,
        actor_id=str(actor_id or ""),
        action=action,
        object_type=object_type,
        object_id=str(object_id or ""),
        metadata_json=redact_secrets_for_audit(metadata or {}),
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def list_audit_events(
    db: Session,
    *,
    workspace_id: str | None = None,
    task_id: int | None = None,
    limit: int = 100,
) -> list[AuditEvent]:
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(max(min(limit, 500), 1))
    if workspace_id:
        query = query.where(AuditEvent.workspace_id == workspace_id)
    if task_id is not None:
        query = query.where(AuditEvent.task_id == task_id)
    return list(db.scalars(query))
