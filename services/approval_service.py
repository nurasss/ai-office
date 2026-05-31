"""Approval persistence and decision helpers."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.models import Approval, utc_now
from core.schemas import ApprovalCreate, TaskEventCreate
from core.task_lifecycle import TASK_CANCELLED, TASK_QUEUED, TASK_WAITING_APPROVAL
from services.audit_service import audit_log
from services.task_service import TaskService


class ApprovalStateError(RuntimeError):
    """Raised when an approval cannot be decided in its current state."""


class ApprovalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_approval(self, payload: ApprovalCreate) -> Approval:
        approval = Approval(
            task_id=payload.task_id,
            action_type=payload.action_type,
            summary=payload.summary,
            payload=payload.payload,
            requested_by_agent=payload.requested_by_agent,
        )
        self.db.add(approval)
        self.db.flush()
        audit_log(
            self.db,
            workspace_id="default",
            task_id=approval.task_id,
            actor_type="system",
            actor_id="approval_service",
            action="tool.approval_requested",
            object_type="approval",
            object_id=approval.id or "",
            metadata={"action_type": approval.action_type, "requested_by_agent": approval.requested_by_agent},
        )
        self.db.commit()
        self.db.refresh(approval)
        if approval.task_id:
            TaskService(self.db).add_event(
                approval.task_id,
                TaskEventCreate(
                    event_type="approval_requested",
                    message=approval.summary,
                    metadata={"approval_id": approval.id, "action_type": approval.action_type},
                ),
            )
        return approval

    def list_approvals(self, status: str | None = None) -> list[Approval]:
        query = select(Approval).order_by(Approval.created_at.desc())
        if status:
            query = query.where(Approval.status == status)
        return list(self.db.scalars(query))

    def get_approval(self, approval_id: int) -> Approval | None:
        return self.db.get(Approval, approval_id)

    def approve(
        self,
        approval_id: int,
        *,
        approved_by: str = "api",
        message: str = "",
    ) -> Approval | None:
        approval = self.get_approval(approval_id)
        if not approval:
            return None
        self._expire_if_ttl_elapsed(approval)
        if approval.status != "pending":
            raise ApprovalStateError(f"Approval {approval.id} is already {approval.status}.")
        approval.status = "approved"
        approval.approved_by = approved_by
        approval.decided_at = utc_now()
        if approval.task_id:
            task = TaskService(self.db).get_task(approval.task_id)
            if task and task.status == "waiting_approval":
                TaskService(self.db)._apply_status(
                    task,
                    TASK_QUEUED,
                    message=f"Approval {approval.id} approved; task returned to queue.",
                    metadata={"approval_id": approval.id},
                )
            TaskService(self.db).add_event(
                approval.task_id,
                TaskEventCreate(
                    event_type="approval_approved",
                    message=message or f"Approval {approval.id} approved.",
                    metadata={"approval_id": approval.id, "approved_by": approved_by},
                ),
                commit=False,
            )
        audit_log(
            self.db,
            workspace_id="default",
            task_id=approval.task_id,
            actor_type="user",
            actor_id=approved_by,
            action="approval.approved",
            object_type="approval",
            object_id=approval.id,
            metadata={"message": message, "tool_call_id": approval.tool_call_id},
        )
        if approval.tool_call_id:
            from tools.registry import ToolExecutionService

            ToolExecutionService(self.db).execute_approved_tool_call(
                approval.tool_call_id,
                approved_by=approved_by,
            )
        self.db.commit()
        self.db.refresh(approval)
        return approval

    def reject(
        self,
        approval_id: int,
        *,
        approved_by: str = "api",
        message: str = "",
    ) -> Approval | None:
        approval = self.get_approval(approval_id)
        if not approval:
            return None
        self._expire_if_ttl_elapsed(approval)
        if approval.status != "pending":
            raise ApprovalStateError(f"Approval {approval.id} is already {approval.status}.")
        approval.status = "rejected"
        approval.approved_by = approved_by
        approval.decided_at = utc_now()
        if approval.task_id:
            task = TaskService(self.db).get_task(approval.task_id)
            if task and task.status == "waiting_approval":
                TaskService(self.db)._apply_status(
                    task,
                    TASK_CANCELLED,
                    message=f"Approval {approval.id} rejected; task cancelled.",
                    metadata={"approval_id": approval.id},
                )
            TaskService(self.db).add_event(
                approval.task_id,
                TaskEventCreate(
                    event_type="approval_rejected",
                    message=message or f"Approval {approval.id} rejected.",
                    metadata={"approval_id": approval.id, "approved_by": approved_by},
                ),
                commit=False,
            )
        audit_log(
            self.db,
            workspace_id="default",
            task_id=approval.task_id,
            actor_type="user",
            actor_id=approved_by,
            action="approval.rejected",
            object_type="approval",
            object_id=approval.id,
            metadata={"message": message, "tool_call_id": approval.tool_call_id},
        )
        self.db.commit()
        self.db.refresh(approval)
        return approval

    def expire_pending(self, *, ttl_hours: int | None = None) -> list[int]:
        """Expire pending approvals older than the configured TTL."""
        ttl = ttl_hours if ttl_hours is not None else get_settings().ai_office_approval_ttl_hours
        cutoff = utc_now() - timedelta(hours=max(ttl, 0))
        query = select(Approval).where(
            Approval.status == "pending",
            Approval.created_at <= cutoff,
        )
        expired_ids: list[int] = []
        task_service = TaskService(self.db)
        for approval in self.db.scalars(query):
            approval.status = "expired"
            approval.decided_at = utc_now()
            expired_ids.append(approval.id)
            if approval.task_id:
                task = task_service.get_task(approval.task_id)
                if task and task.status == TASK_WAITING_APPROVAL:
                    task_service._apply_status(
                        task,
                        TASK_CANCELLED,
                        message=f"Approval {approval.id} expired; task cancelled.",
                        metadata={"approval_id": approval.id, "ttl_hours": ttl},
                    )
                task_service.add_event(
                    approval.task_id,
                    TaskEventCreate(
                        event_type="approval_expired",
                        message=f"Approval {approval.id} expired after {ttl} hours.",
                        metadata={"approval_id": approval.id, "ttl_hours": ttl},
                    ),
                    commit=False,
                )
        if expired_ids:
            self.db.commit()
        return expired_ids

    def count_by_status(self) -> dict[str, int]:
        rows = self.db.execute(select(Approval.status, func.count(Approval.id)).group_by(Approval.status)).all()
        return {str(status): int(count) for status, count in rows}

    def _expire_if_ttl_elapsed(self, approval: Approval) -> None:
        if approval.status != "pending":
            return
        ttl = get_settings().ai_office_approval_ttl_hours
        cutoff = utc_now() - timedelta(hours=max(ttl, 0))
        created_at = approval.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=utc_now().tzinfo)
        if created_at > cutoff:
            return
        approval.status = "expired"
        approval.decided_at = utc_now()
        if approval.task_id:
            task_service = TaskService(self.db)
            task = task_service.get_task(approval.task_id)
            if task and task.status == TASK_WAITING_APPROVAL:
                task_service._apply_status(
                    task,
                    TASK_CANCELLED,
                    message=f"Approval {approval.id} expired; task cancelled.",
                    metadata={"approval_id": approval.id, "ttl_hours": ttl},
                )
            task_service.add_event(
                approval.task_id,
                TaskEventCreate(
                    event_type="approval_expired",
                    message=f"Approval {approval.id} expired before decision.",
                    metadata={"approval_id": approval.id, "ttl_hours": ttl},
                ),
                commit=False,
            )
        self.db.commit()
