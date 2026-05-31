"""Autonomous runtime API: projects, tasks, approvals, and scheduler hooks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.auth import require_api_key, require_permission
from core.config import get_settings
from core.db import database_connected, get_db, redis_connected
from core.models import KnowledgeDocument, ModelUsage, TaskRun
from core.schemas import (
    AuditEventRead,
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
    TaskRunRead,
    TaskStatusUpdate,
)
from services.audit_service import list_audit_events
from services.approval_service import ApprovalService, ApprovalStateError
from services.autonomy_service import AutonomyService, get_autonomy_enabled
from services.project_service import ProjectService
from services.scheduler import autonomy_scheduler
from services.task_service import TaskService
from tools.external.telegram import telegram_runtime_configured
from workers.rq_queue import enqueue_task_rq
from rag.ingestion import ingest_text
from rag.retrieval import retrieve_context

router = APIRouter(
    prefix="/api",
    tags=["autonomous-runtime"],
    dependencies=[Depends(require_api_key)],
)


class KnowledgeUploadRequest(BaseModel):
    workspace_id: str = "default"
    agent_namespace: str = Field(default="agent_support")
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    source_uri: str = "api_upload"
    file_type: str = "md"


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
    task_payload = payload.model_copy(update={"status": "pending"} if payload.status == "planned" else {})
    task = TaskService(db).create_task(task_payload)
    enqueue_task_rq(task.id)
    db.refresh(task)
    return task


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


@router.post("/tasks/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(task_id: int, db: Session = Depends(get_db)):
    task = TaskService(db).update_status(task_id, "cancelled", message="Task cancelled by API.")
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.get("/tasks/{task_id}/runs", response_model=list[TaskRunRead])
async def list_task_runs(task_id: int, db: Session = Depends(get_db)):
    if not TaskService(db).get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found.")
    query = select(TaskRun).where(TaskRun.task_id == task_id).order_by(TaskRun.started_at.desc())
    return list(db.scalars(query))


@router.get("/tasks/{task_id}/audit", response_model=list[AuditEventRead])
async def list_task_audit(task_id: int, db: Session = Depends(get_db)):
    if not TaskService(db).get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found.")
    return list_audit_events(db, task_id=task_id)


@router.get("/tasks/{task_id}/events", response_model=list[TaskEventRead])
async def list_task_events(task_id: int, db: Session = Depends(get_db)):
    if not TaskService(db).get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskService(db).list_events(task_id)


@router.get("/approvals", response_model=list[ApprovalRead])
async def list_approvals(
    status: str | None = Query(default=None),
    _permission: None = Depends(require_permission("approval:read")),
    db: Session = Depends(get_db),
):
    return ApprovalService(db).list_approvals(status=status)


@router.get("/approvals/{approval_id}", response_model=ApprovalRead)
async def get_approval(
    approval_id: int,
    _permission: None = Depends(require_permission("approval:read")),
    db: Session = Depends(get_db),
):
    approval = ApprovalService(db).get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found.")
    return approval


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRead)
async def approve_approval(
    approval_id: int,
    payload: ApprovalDecision | None = None,
    _permission: None = Depends(require_permission("approval:decide")),
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
    _permission: None = Depends(require_permission("approval:decide")),
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
    telegram_configured = telegram_runtime_configured()
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


@router.get("/audit", response_model=list[AuditEventRead])
async def list_audit(
    workspace_id: str | None = Query(default=None),
    task_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _permission: None = Depends(require_permission("audit:read")),
    db: Session = Depends(get_db),
):
    return list_audit_events(db, workspace_id=workspace_id, task_id=task_id, limit=limit)


@router.get("/metrics/summary")
async def metrics_summary(db: Session = Depends(get_db)):
    tasks_today = int(db.scalar(select(func.count()).select_from(TaskRun)) or 0)
    completed = int(db.scalar(select(func.count()).select_from(TaskRun).where(TaskRun.status == "completed")) or 0)
    failed = int(db.scalar(select(func.count()).select_from(TaskRun).where(TaskRun.status == "failed")) or 0)
    pending_approvals = ApprovalService(db).count_by_status().get("pending", 0)
    total_cost = float(db.scalar(select(func.coalesce(func.sum(ModelUsage.cost_usd), 0.0))) or 0.0)
    total_tokens = int(
        db.scalar(select(func.coalesce(func.sum(ModelUsage.input_tokens + ModelUsage.output_tokens), 0))) or 0
    )
    return {
        "tasks_today": tasks_today,
        "tasks_completed": completed,
        "tasks_failed": failed,
        "pending_approvals": pending_approvals,
        "total_cost_usd_today": total_cost,
        "total_tokens_today": total_tokens,
        "tool_success_rate": 1.0,
        "avg_task_latency_ms": 0,
    }


@router.get("/costs/summary")
async def costs_summary(db: Session = Depends(get_db)):
    total_cost = float(db.scalar(select(func.coalesce(func.sum(ModelUsage.cost_usd), 0.0))) or 0.0)
    total_input = int(db.scalar(select(func.coalesce(func.sum(ModelUsage.input_tokens), 0))) or 0)
    total_output = int(db.scalar(select(func.coalesce(func.sum(ModelUsage.output_tokens), 0))) or 0)
    return {"total_cost_usd": total_cost, "input_tokens": total_input, "output_tokens": total_output}


@router.get("/costs/by-agent")
async def costs_by_agent(db: Session = Depends(get_db)):
    rows = db.execute(
        select(ModelUsage.agent_run_id, func.coalesce(func.sum(ModelUsage.cost_usd), 0.0)).group_by(ModelUsage.agent_run_id)
    ).all()
    return [{"agent_run_id": agent_run_id, "cost_usd": float(cost)} for agent_run_id, cost in rows]


@router.get("/costs/by-model")
async def costs_by_model(db: Session = Depends(get_db)):
    rows = db.execute(
        select(ModelUsage.provider, ModelUsage.model, func.coalesce(func.sum(ModelUsage.cost_usd), 0.0)).group_by(
            ModelUsage.provider, ModelUsage.model
        )
    ).all()
    return [{"provider": provider, "model": model, "cost_usd": float(cost)} for provider, model, cost in rows]


@router.post("/knowledge/upload")
async def upload_knowledge(payload: KnowledgeUploadRequest, db: Session = Depends(get_db)):
    return ingest_text(
        db,
        workspace_id=payload.workspace_id,
        agent_namespace=payload.agent_namespace,
        title=payload.title,
        source_uri=payload.source_uri,
        file_type=payload.file_type,
        content=payload.content,
    )


@router.get("/knowledge/documents")
async def list_knowledge_documents(
    workspace_id: str = Query(default="default"),
    agent_namespace: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace_id).order_by(
        KnowledgeDocument.created_at.desc()
    )
    if agent_namespace:
        stmt = stmt.where(KnowledgeDocument.agent_namespace == agent_namespace)
    return [
        {
            "id": document.id,
            "title": document.title,
            "agent_namespace": document.agent_namespace,
            "source_uri": document.source_uri,
            "file_type": document.file_type,
            "version": document.version,
            "created_at": document.created_at.isoformat(),
        }
        for document in db.scalars(stmt)
    ]


@router.get("/knowledge/search")
async def search_knowledge(
    query: str = Query(min_length=1),
    agent_namespace: str = Query(default="agent_support"),
    workspace_id: str = Query(default="default"),
    top_k: int = Query(default=6, ge=1, le=20),
    db: Session = Depends(get_db),
):
    return retrieve_context(
        db,
        query=query,
        agent_namespace=agent_namespace,
        workspace_id=workspace_id,
        top_k=top_k,
    )


@router.post("/autonomy/daily-plan", response_model=DailyPlanResponse)
async def run_daily_plan(db: Session = Depends(get_db)):
    return await AutonomyService(db).daily_plan(notify=True)


@router.post("/autonomy/review")
async def run_evening_review(db: Session = Depends(get_db)):
    return await AutonomyService(db).evening_review(notify=True)
