"""Task lifecycle constants and retry/stuck helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

TASK_PLANNED = "planned"
TASK_PENDING = "pending"
TASK_QUEUED = "queued"
TASK_RUNNING = "running"
TASK_WAITING_APPROVAL = "waiting_approval"
TASK_BLOCKED = "blocked"
TASK_COMPLETED = "completed"
TASK_FAILED = "failed"
TASK_CANCELLED = "cancelled"
TASK_STUCK = "stuck"

OPEN_TASK_STATUSES = {
    TASK_PLANNED,
    TASK_PENDING,
    TASK_QUEUED,
    TASK_RUNNING,
    TASK_WAITING_APPROVAL,
    TASK_BLOCKED,
    TASK_STUCK,
}

FINAL_TASK_STATUSES = {
    TASK_COMPLETED,
    TASK_CANCELLED,
}

RETRYABLE_TASK_STATUSES = {
    TASK_FAILED,
    TASK_STUCK,
}


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def is_older_than(value: datetime | None, *, minutes: int) -> bool:
    """Return whether a timestamp is older than a timeout."""
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= utc_now() - timedelta(minutes=max(minutes, 0))
