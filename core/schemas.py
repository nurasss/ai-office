"""Pydantic schemas for autonomous runtime APIs and services."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ProjectStatus = Literal["active", "paused", "archived"]
TaskStatus = Literal[
    "planned",
    "pending",
    "queued",
    "running",
    "waiting_approval",
    "blocked",
    "completed",
    "failed",
    "cancelled",
    "stuck",
]
AgentId = Literal[
    "pmo",
    "developer",
    "research",
    "memory",
    "copywriter",
    "data_analyst",
    "support",
    "strategist",
    "accountant",
]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired"]


class ProjectCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    goal: str = ""
    status: ProjectStatus = "active"
    priority: int = Field(default=3, ge=1, le=5)


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    goal: str | None = None
    status: ProjectStatus | None = None
    priority: int | None = Field(default=None, ge=1, le=5)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str
    goal: str
    status: str
    priority: int
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    workspace_id: str = "default"
    project_slug: str | None = None
    project_id: int | None = None
    title: str = Field(min_length=1, max_length=255)
    input_text: str = ""
    description: str = ""
    created_by: Literal["user", "pmo", "scheduler", "agent"] = "user"
    assigned_agent: AgentId = "pmo"
    agent_hint: AgentId | None = None
    status: TaskStatus = "planned"
    risk_level: Literal["safe", "low", "medium", "high", "critical"] = "safe"
    priority: int = Field(default=3, ge=1, le=5)
    requires_approval: bool = False
    due_at: datetime | None = None
    base_agent: str | None = None
    profile_id: str | None = None
    profile_name: str | None = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus
    message: str = ""


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str
    workspace_id: str | None
    project_id: int | None
    title: str
    input_text: str
    description: str
    created_by: str
    assigned_agent: str
    status: str
    risk_level: str
    priority: int
    requires_approval: bool
    retry_count: int
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    result_summary: str | None
    result_payload: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class TaskEventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskEventRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: int
    task_id: int
    event_type: str
    message: str
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="metadata_json",
        serialization_alias="metadata",
    )
    created_at: datetime


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    task_run_id: int | None = None
    task_id: int | None
    agent_id: str
    agent_name: str = ""
    model_provider: str = ""
    model_name: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    status: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ApprovalCreate(BaseModel):
    task_id: int | None = None
    action_type: str = Field(min_length=1, max_length=128)
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_by_agent: str = "pmo"


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int | None
    tool_call_id: int | None = None
    action_type: str
    tool_name: str = ""
    risk_level: str = ""
    summary: str
    reason: str = ""
    arguments_json: dict[str, Any] = Field(default_factory=dict)
    dry_run_result: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any]
    status: str
    requested_by_agent: str
    approved_by: str | None
    created_at: datetime
    decided_at: datetime | None


class ApprovalDecision(BaseModel):
    approved_by: str = "telegram"
    message: str = ""


class TaskRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    error_message: str | None
    trace_id: str


class ToolCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int | None
    task_run_id: int | None
    agent_run_id: int | None
    tool_name: str
    arguments_json: dict[str, Any]
    result_json: dict[str, Any] | None
    status: str
    risk_level: str
    requires_approval: bool
    approval_id: int | None
    idempotency_key: str
    created_at: datetime
    finished_at: datetime | None


class AuditEventRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: int
    workspace_id: str | None
    task_id: int | None
    actor_type: str
    actor_id: str
    action: str
    object_type: str
    object_id: str
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="metadata_json",
        serialization_alias="metadata",
    )
    created_at: datetime


class TaskCreateResponse(BaseModel):
    task_id: str
    status: str


class PMOTaskPlanItem(BaseModel):
    title: str
    description: str = ""
    assigned_agent: AgentId = "pmo"
    priority: int = Field(default=3, ge=1, le=5)
    requires_approval: bool = False
    base_agent: str | None = None
    profile_id: str | None = None
    profile_name: str | None = None


class PMOStructuredPlan(BaseModel):
    project_slug: str
    goal: str
    tasks: list[PMOTaskPlanItem]
    fallback_used: bool = False


class DailyPlanResponse(BaseModel):
    status: str
    summary: str
    created_task_ids: list[int] = Field(default_factory=list)
    project_slugs: list[str] = Field(default_factory=list)


class AutonomyStatusResponse(BaseModel):
    enabled: bool
    scheduler_running: bool
    poll_interval_seconds: int
    daily_plan_hour: int
    evening_review_hour: int
    timezone: str


class RuntimeSchedulerStatus(BaseModel):
    enabled: bool
    running: bool
    last_daily_plan_run_at: str | None = None
    last_evening_review_run_at: str | None = None
    last_poll_run_at: str | None = None


class RuntimeStatusResponse(BaseModel):
    autonomy_enabled: bool
    scheduler: RuntimeSchedulerStatus
    tasks: dict[str, int]
    approvals: dict[str, int]
    database: dict[str, bool]


class RuntimeHealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    database: bool
    scheduler: bool
    autonomy_enabled: bool
    telegram_configured: bool
    model_keys: dict[str, bool]
