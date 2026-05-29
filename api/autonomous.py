"""Autonomous runtime API: projects, tasks, approvals, and scheduler hooks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.auth import require_api_key
from core.config import get_settings
from core.db import database_connected, get_db
from core.schemas import (
    ApprovalDecision,
    ApprovalRead,
    AutonomyStatusResponse,
    DailyPlanResponse,
    ProjectCreate,
    ProjectRead,
    RuntimeHealthResponse,
    RuntimeSchedulerStatus,
    RuntimeStatusResponse,
    TaskCreate,
    TaskEventRead,
    TaskRead,
    TaskStatusUpdate,
)
from services.approval_service import ApprovalService, ApprovalStateError
from services.autonomy_service import AutonomyService, get_autonomy_enabled
from services.project_service import ProjectService
from services.scheduler import autonomy_scheduler
from services.task_service import TaskService

router = APIRouter(
    prefix="/api",
    tags=["autonomous-runtime"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return ProjectService(db).list_projects(status=status)


@router.post("/projects", response_model=ProjectRead)
async def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    return ProjectService(db).create_project(payload)


@router.get("/projects/{slug}", response_model=ProjectRead)
async def get_project(slug: str, db: Session = Depends(get_db)):
    project = ProjectService(db).get_project_by_slug(slug)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@router.get("/tasks", response_model=list[TaskRead])
async def list_tasks(
    status: str | None = Query(default=None),
    project_slug: str | None = Query(default=None),
    assigned_agent: str | None = Query(default=None),
    open_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return TaskService(db).list_tasks(
        status=status,
        project_slug=project_slug,
        assigned_agent=assigned_agent,
        open_only=open_only,
    )


@router.post("/tasks", response_model=TaskRead)
async def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    return TaskService(db).create_task(payload)


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, db: Session = Depends(get_db)):
    task = TaskService(db).get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.post("/tasks/{task_id}/run")
async def run_task(task_id: int, db: Session = Depends(get_db)):
    result = TaskService(db).run_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found.")
    return result


@router.post("/tasks/{task_id}/status", response_model=TaskRead)
async def update_task_status(
    task_id: int,
    payload: TaskStatusUpdate,
    db: Session = Depends(get_db),
):
    task = TaskService(db).update_status(task_id, payload.status, message=payload.message)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.get("/tasks/{task_id}/events", response_model=list[TaskEventRead])
async def list_task_events(task_id: int, db: Session = Depends(get_db)):
    if not TaskService(db).get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskService(db).list_events(task_id)


@router.get("/approvals", response_model=list[ApprovalRead])
async def list_approvals(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return ApprovalService(db).list_approvals(status=status)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRead)
async def approve_approval(
    approval_id: int,
    payload: ApprovalDecision | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or ApprovalDecision()
    try:
        approval = ApprovalService(db).approve(
            approval_id,
            approved_by=payload.approved_by,
            message=payload.message,
        )
    except ApprovalStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found.")
    return approval


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRead)
async def reject_approval(
    approval_id: int,
    payload: ApprovalDecision | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or ApprovalDecision()
    try:
        approval = ApprovalService(db).reject(
            approval_id,
            approved_by=payload.approved_by,
            message=payload.message,
        )
    except ApprovalStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found.")
    return approval


@router.get("/autonomy/status", response_model=AutonomyStatusResponse)
async def autonomy_status():
    settings = get_settings()
    return AutonomyStatusResponse(
        enabled=get_autonomy_enabled(),
        scheduler_running=autonomy_scheduler.running,
        poll_interval_seconds=settings.autonomy_poll_interval_seconds,
        daily_plan_hour=settings.autonomy_daily_plan_hour,
        evening_review_hour=settings.autonomy_evening_review_hour,
        timezone=settings.autonomy_timezone,
    )


@router.get("/autonomous/status", response_model=RuntimeStatusResponse)
async def autonomous_status(db: Session = Depends(get_db)):
    settings = get_settings()
    task_counts = TaskService(db).count_by_status()
    approval_counts = ApprovalService(db).count_by_status()
    for status in ["queued", "running", "waiting_approval", "failed", "stuck"]:
        task_counts.setdefault(status, 0)
    task_counts["completed_today"] = TaskService(db).completed_today_count()
    approval_counts.setdefault("pending", 0)
    approval_counts.setdefault("expired", 0)
    return RuntimeStatusResponse(
        autonomy_enabled=get_autonomy_enabled(),
        scheduler=RuntimeSchedulerStatus(
            enabled=settings.autonomy_enabled,
            running=autonomy_scheduler.running,
            last_daily_plan_run_at=autonomy_scheduler.last_daily_plan_run_at,
            last_evening_review_run_at=autonomy_scheduler.last_evening_review_run_at,
            last_poll_run_at=autonomy_scheduler.last_poll_run_at,
        ),
        tasks=task_counts,
        approvals=approval_counts,
        database={"connected": database_connected()},
    )


@router.get("/autonomous/health", response_model=RuntimeHealthResponse)
async def autonomous_health():
    settings = get_settings()
    telegram_configured = bool(
        settings.telegram_bot_token.strip()
        and settings.telegram_chat_id.strip()
        and settings.telegram_webhook_secret.strip()
        and settings.allowed_telegram_user_ids.strip()
        and settings.allowed_telegram_chat_ids.strip()
    )
    db_ok = database_connected()
    return RuntimeHealthResponse(
        status="ok" if db_ok else "degraded",
        database=db_ok,
        scheduler=autonomy_scheduler.running,
        autonomy_enabled=get_autonomy_enabled(),
        telegram_configured=telegram_configured,
        model_keys={
            "openai": bool(settings.openai_api_key.strip()),
            "anthropic": bool(settings.anthropic_api_key.strip()),
            "google": bool(settings.google_api_key.strip()),
        },
    )


@router.post("/autonomy/daily-plan", response_model=DailyPlanResponse)
async def run_daily_plan(db: Session = Depends(get_db)):
    return await AutonomyService(db).daily_plan(notify=True)


@router.post("/autonomy/review")
async def run_evening_review(db: Session = Depends(get_db)):
    return await AutonomyService(db).evening_review(notify=True)
