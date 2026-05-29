# Autonomous Runtime

Текущий runtime — личный 24/7 MVP: без Celery/RQ, но с четким разделением на DB, service layer, Telegram commands, scheduler и approval policy.

## Components

- `core/db.py`, `core/models.py`, `core/schemas.py`: SQLAlchemy persistence.
- `services/project_service.py`: projects CRUD and default personal project seeds.
- `services/task_service.py`: tasks, task events, safe MVP task execution, agent runs.
- `services/approval_service.py`: approve/reject workflow.
- `services/autonomy_service.py`: daily plan, queued-task polling, evening review.
- `services/scheduler.py`: in-process scheduler started by FastAPI when `AUTONOMY_ENABLED=true`.
- `core/action_policy.py`: safe/read/prepare/approval/forbidden decisions.

## Database

Local default:

```text
DATABASE_URL=sqlite:///data/ai_office.db
```

Recommended for 24/7:

```text
DATABASE_URL=postgresql+psycopg2://ai_office:<password>@postgres:5432/ai_office
```

For persistent VPS/PostgreSQL deployments, prefer Alembic:

```bash
alembic upgrade head
```

`init_db()` still exists for local smoke runs and tests. New migrations can be created later with:

```bash
alembic revision --autogenerate -m "describe_change"
alembic upgrade head
```

## API

All autonomous endpoints require `AI_OFFICE_API_KEY` in either:

```text
X-API-Key: <value>
Authorization: Bearer <value>
```

Main endpoints:

```text
GET  /api/projects
POST /api/projects
GET  /api/projects/{slug}
GET  /api/tasks
POST /api/tasks
GET  /api/tasks/{task_id}
POST /api/tasks/{task_id}/run
POST /api/tasks/{task_id}/status
GET  /api/tasks/{task_id}/events
GET  /api/approvals
POST /api/approvals/{approval_id}/approve
POST /api/approvals/{approval_id}/reject
GET  /api/autonomy/status
GET  /api/autonomous/status
GET  /api/autonomous/health
POST /api/autonomy/daily-plan
POST /api/autonomy/review
```

## Scheduler

Set:

```text
AUTONOMY_ENABLED=true
AUTONOMY_DAILY_PLAN_HOUR=9
AUTONOMY_EVENING_REVIEW_HOUR=19
AUTONOMY_POLL_INTERVAL_SECONDS=1800
AUTONOMY_TIMEZONE=Asia/Almaty
AI_OFFICE_TASK_STUCK_TIMEOUT_MINUTES=30
AI_OFFICE_TASK_MAX_RETRIES=2
AI_OFFICE_APPROVAL_TTL_HOURS=24
```

Loops:

- Daily plan: checks active projects and creates safe queued PMO tasks when a project has no open tasks.
- Task polling: expires old approvals, detects stuck running tasks, retries retryable failures, runs queued safe tasks as draft results, and moves dangerous tasks to `waiting_approval`.
- Evening review: summarizes the day and stores a DB memory summary.

## Task Lifecycle

Core runtime statuses:

```text
queued
running
completed
failed
waiting_approval
cancelled
stuck
```

Every status transition writes a `task_event` with `from_status`, `to_status`, and a reason. Running tasks older than `AI_OFFICE_TASK_STUCK_TIMEOUT_MINUTES` are retried while `retry_count < AI_OFFICE_TASK_MAX_RETRIES`; otherwise they become `stuck`. Failed tasks use the same retry budget.

Pending approvals older than `AI_OFFICE_APPROVAL_TTL_HOURS` become `expired`. A task that was only waiting for permission becomes `cancelled`, and expired approvals cannot be approved later.

## PMO Planning

`PMOAgent.plan_goal()` and `PMOPlanningService` expect structured JSON when an LLM is available. If JSON is invalid or no LLM key exists, the deterministic fallback creates one task, assigns an agent by keyword, and marks dangerous work as requiring approval.

## Agent Profiles

AI Office supports optional curated agent profiles adapted from `agency-agents`.
Profiles specialize existing agents, for example `developer.mcp_builder` or
`copywriter.technical_writer`, and are selected through deterministic keyword
routing. Profile metadata can be attached to PMO plans and task events.

Profiles do not override approvals, action policy, Telegram allowlists, API
auth, CORS, scheduler behavior, or safe developer tools.
