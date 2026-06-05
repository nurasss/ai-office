"""FastAPI веб-интерфейс для AI Office."""

from __future__ import annotations

import asyncio
import html
import hmac
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from agents import (
    AccountantAgent,
    CopywriterAgent,
    DataAnalystAgent,
    DeveloperAgent,
    PMOAgent,
    StrategistAgent,
    SupportAgent,
)
from core.agent_events import (
    format_sse,
    get_agent_statuses,
    publish_agent_status,
    reset_agent_status_later,
    subscribe_agent_events,
)
from core.auth import parse_id_allowlist, require_admin, require_api_key
from core.chat_history import ChatHistoryStore, ChatMessage, utc_now_iso
from core.config import get_settings
from core.db import database_connected, get_session, init_db, redis_connected, should_auto_create_tables
from core.llm_router import MissingLLMCredentialsError
from core.logger import get_logger, setup_logging
from core.models import (
    AgentRun,
    Approval,
    AuditEvent,
    GeneratedSite,
    GeneratedTool,
    Goal,
    KnowledgeDocument,
    Memory,
    ModelUsage,
    Task,
    TaskRun,
    ToolCall,
    UserProfile,
)
from core.production import run_production_preflight
from core.schemas import TaskCreate, TaskEventCreate
from api.autonomous import router as autonomous_router
from services.audit_service import audit_log
from services.approval_service import ApprovalService, ApprovalStateError
from services.artifact_generation_service import ArtifactGenerationService
from services.autonomy_service import AutonomyService, get_autonomy_enabled, set_autonomy_enabled
from services.goal_engine_service import GoalEngineService
from services.profile_memory_service import ProfileMemoryService
from services.project_service import ProjectService, slugify
from services.scheduler import autonomy_scheduler
from services.task_service import TaskService
from tools.base import ToolContext
from tools.external.telegram import (
    approval_inline_keyboard,
    send_telegram_message,
    send_telegram_message_to,
    telegram_runtime_configured,
)
from tools.registry import ToolExecutionService

load_dotenv()
setup_logging("INFO")
logger = get_logger("web")

app = FastAPI(title="AI Office", version="1.0.0")
settings = get_settings()
allowed_origins = settings.allowed_origins_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(autonomous_router)
templates = Jinja2Templates(directory="templates")

# ── Кэш агентов (lazy init) ──────────────────────────────────────────
_agents: dict[str, object] = {}
chat_store = ChatHistoryStore()

AGENT_NAMES = {
    "pmo": "PMO",
    "data_analyst": "Аналитик",
    "developer": "Разработчик",
    "copywriter": "Копирайтер",
    "support": "Поддержка",
    "strategist": "Стратег",
    "accountant": "Бухгалтер",
}

SPECIALIST_AGENT_IDS = [
    "data_analyst",
    "developer",
    "copywriter",
    "support",
    "strategist",
    "accountant",
]

TELEGRAM_AGENT_ALIASES = {
    "pmo": "pmo",
    "пмо": "pmo",
    "аналитик": "data_analyst",
    "analytics": "data_analyst",
    "analyst": "data_analyst",
    "data": "data_analyst",
    "data_analyst": "data_analyst",
    "developer": "developer",
    "dev": "developer",
    "разработчик": "developer",
    "копирайтер": "copywriter",
    "copywriter": "copywriter",
    "writer": "copywriter",
    "support": "support",
    "поддержка": "support",
    "стратег": "strategist",
    "strategist": "strategist",
    "бухгалтер": "accountant",
    "accountant": "accountant",
}

TELEGRAM_THREAD_FIELDS = {
    "general": "telegram_general_thread_id",
    "pmo": "telegram_pmo_thread_id",
    "data_analyst": "telegram_data_analyst_thread_id",
    "developer": "telegram_developer_thread_id",
    "copywriter": "telegram_copywriter_thread_id",
    "support": "telegram_support_thread_id",
    "strategist": "telegram_strategist_thread_id",
    "accountant": "telegram_accountant_thread_id",
}


@app.on_event("startup")
async def startup_autonomous_runtime() -> None:
    """Initialize persistence and start the optional autonomous scheduler."""
    try:
        run_production_preflight(raise_on_error=True)
        if should_auto_create_tables():
            init_db()
    except Exception as error:
        logger.error("db.init.failed", error=str(error), exc_info=True)
        raise

    if get_autonomy_enabled():
        autonomy_scheduler.start()


@app.on_event("shutdown")
async def shutdown_autonomous_runtime() -> None:
    """Stop the in-process scheduler cleanly on shutdown."""
    await autonomy_scheduler.stop()


@app.get("/ready")
async def ready() -> dict[str, object]:
    db_ok = database_connected()
    redis_ok = redis_connected()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "redis": redis_ok,
        "worker_backend": get_settings().worker_backend,
        "queue_name": get_settings().rq_queue_name,
        "config": {
            "environment": str(get_settings().environment.value),
            "real_tools_enabled": get_settings().enable_real_tools,
        },
    }


def _admin_page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<style>body{font-family:system-ui;margin:24px;max-width:1200px}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}"
        "td,th{border:1px solid #ddd;padding:6px;text-align:left;vertical-align:top}"
        "code,pre{background:#f6f6f6;padding:2px 4px;border-radius:4px}"
        "button{padding:6px 10px;margin:2px}</style></head><body>"
        "<nav><a href='/admin/tasks'>Tasks</a> | <a href='/admin/approvals'>Approvals</a> | "
        "<a href='/admin/audit'>Audit</a> | <a href='/admin/costs'>Costs</a> | "
        "<a href='/admin/knowledge'>Knowledge</a></nav>"
        f"<h1>{title}</h1>{body}</body></html>"
    )


def _product_page(title: str, body: str, *, subtitle: str = "") -> HTMLResponse:
    navigation = [
        ("/dashboard", "Dashboard"),
        ("/agents", "Agents"),
        ("/goals", "Goals"),
        ("/tasks", "Tasks"),
        ("/sites", "Sites"),
        ("/tools", "Tools"),
        ("/memory", "Memory"),
        ("/landing", "Landing"),
    ]
    nav_html = " ".join(
        f"<a href='{href}'>{label}</a>" for href, label in navigation
    )
    subtitle_html = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<style>"
        ":root{color-scheme:dark;--bg:#0f1115;--panel:#171a21;--line:#282c35;--text:#f3f4f6;--muted:#9ca3af;--accent:#5b8def;}"
        "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}"
        "main{max-width:1180px;margin:0 auto;padding:24px}"
        "nav{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 18px}"
        "nav a{text-decoration:none;color:#dbeafe;background:#1e2633;border:1px solid #334155;border-radius:999px;padding:8px 12px;font-size:13px}"
        "header{display:grid;gap:6px;margin-bottom:18px}header h1{margin:0;font-size:28px}header p{margin:0;color:var(--muted)}"
        ".panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px;margin-bottom:14px}"
        ".grid{display:grid;gap:14px}.cards{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}"
        ".card{background:#1c2028;border:1px solid var(--line);border-radius:8px;padding:14px}"
        ".muted{color:var(--muted)}.pill{display:inline-flex;background:#1f2b3f;color:#dbeafe;border-radius:999px;padding:4px 9px;font-size:12px}"
        ".list{display:grid;gap:10px}.row{border:1px solid var(--line);border-radius:8px;background:#1c2028;padding:12px}"
        ".row strong{display:block;margin-bottom:4px}.row p{margin:4px 0;color:var(--muted)}"
        "table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}"
        "code,pre{background:#10151d;border-radius:6px;padding:2px 6px;overflow:auto}a{color:#8cc2ff}"
        "@media(max-width:900px){main{padding:18px}}"
        "</style></head><body><main>"
        f"<nav>{nav_html}</nav>"
        f"<header><h1>{html.escape(title)}</h1>{subtitle_html}</header>"
        f"{body}</main></body></html>"
    )


@app.get("/admin/tasks")
async def admin_tasks(_: None = Depends(require_admin)) -> HTMLResponse:
    with get_session() as db:
        rows = db.scalars(select(Task).order_by(Task.created_at.desc()).limit(100)).all()
    body = "<table><tr><th>ID</th><th>Title</th><th>Status</th><th>Agent</th><th>Risk</th><th>Created</th></tr>"
    for task in rows:
        body += (
            f"<tr><td><a href='/admin/tasks/{task.id}'>{task.id}</a></td><td>{task.title}</td>"
            f"<td>{task.status}</td><td>{task.assigned_agent}</td><td>{task.risk_level}</td>"
            f"<td>{task.created_at}</td></tr>"
        )
    return _admin_page("Tasks", body + "</table>")


@app.get("/admin/tasks/{task_id}")
async def admin_task_detail(task_id: int, _: None = Depends(require_admin)) -> HTMLResponse:
    with get_session() as db:
        task = db.get(Task, task_id)
        if not task:
            return _admin_page("Task not found", "<p>Task not found.</p>")
        task_runs = db.scalars(select(TaskRun).where(TaskRun.task_id == task_id)).all()
        agent_runs = db.scalars(select(AgentRun).where(AgentRun.task_id == task_id)).all()
        tool_calls = db.scalars(select(ToolCall).where(ToolCall.task_id == task_id)).all()
        approvals = db.scalars(select(Approval).where(Approval.task_id == task_id)).all()
        audit = db.scalars(select(AuditEvent).where(AuditEvent.task_id == task_id).order_by(AuditEvent.created_at.desc())).all()
    body = f"<h2>{task.title}</h2><p>Status: <b>{task.status}</b></p><pre>{task.input_text}</pre><pre>{task.result_summary or ''}</pre>"
    body += f"<h3>Task runs</h3><pre>{[run.status for run in task_runs]}</pre>"
    body += f"<h3>Agent runs</h3><pre>{[(run.agent_id, run.status) for run in agent_runs]}</pre>"
    body += f"<h3>Tool calls</h3><pre>{[(call.tool_name, call.status) for call in tool_calls]}</pre>"
    body += f"<h3>Approvals</h3><pre>{[(approval.id, approval.status) for approval in approvals]}</pre>"
    body += f"<h3>Audit</h3><pre>{[(event.action, event.created_at.isoformat()) for event in audit]}</pre>"
    return _admin_page(f"Task {task_id}", body)


@app.get("/admin/approvals")
async def admin_approvals(_: None = Depends(require_admin)) -> HTMLResponse:
    with get_session() as db:
        approvals = db.scalars(select(Approval).order_by(Approval.created_at.desc()).limit(100)).all()
    body = "<table><tr><th>ID</th><th>Status</th><th>Tool</th><th>Risk</th><th>Dry run</th><th>Actions</th></tr>"
    for approval in approvals:
        body += (
            f"<tr><td>{approval.id}</td><td>{approval.status}</td><td>{approval.tool_name or approval.action_type}</td>"
            f"<td>{approval.risk_level}</td><td><pre>{approval.dry_run_result}</pre></td>"
            f"<td><form method='post' action='/api/approvals/{approval.id}/approve' style='display:inline'><button>Approve</button></form>"
            f"<form method='post' action='/api/approvals/{approval.id}/reject' style='display:inline'><button>Reject</button></form></td></tr>"
        )
    return _admin_page("Approvals", body + "</table>")


@app.get("/admin/audit")
async def admin_audit(
    task_id: int | None = None,
    action: str | None = None,
    _: None = Depends(require_admin),
) -> HTMLResponse:
    with get_session() as db:
        stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(200)
        if task_id is not None:
            stmt = stmt.where(AuditEvent.task_id == task_id)
        if action:
            stmt = stmt.where(AuditEvent.action == action)
        events = db.scalars(stmt).all()
    body = "<form><input name='task_id' placeholder='task_id'><input name='action' placeholder='action'><button>Filter</button></form>"
    body += "<table><tr><th>Time</th><th>Task</th><th>Action</th><th>Actor</th><th>Object</th><th>Metadata</th></tr>"
    for event in events:
        body += f"<tr><td>{event.created_at}</td><td>{event.task_id or ''}</td><td>{event.action}</td><td>{event.actor_type}:{event.actor_id}</td><td>{event.object_type}:{event.object_id}</td><td><pre>{event.metadata_json}</pre></td></tr>"
    return _admin_page("Audit", body + "</table>")


@app.get("/admin/costs")
async def admin_costs(_: None = Depends(require_admin)) -> HTMLResponse:
    with get_session() as db:
        total_cost = float(db.scalar(select(func.coalesce(func.sum(ModelUsage.cost_usd), 0.0))) or 0.0)
        total_tokens = int(db.scalar(select(func.coalesce(func.sum(ModelUsage.input_tokens + ModelUsage.output_tokens), 0))) or 0)
        by_model = db.execute(select(ModelUsage.provider, ModelUsage.model, func.sum(ModelUsage.cost_usd)).group_by(ModelUsage.provider, ModelUsage.model)).all()
    body = f"<p>Total cost: {total_cost}</p><p>Total tokens: {total_tokens}</p><h2>By model</h2><pre>{by_model}</pre>"
    return _admin_page("Costs", body)


@app.get("/admin/knowledge")
async def admin_knowledge(
    query: str | None = None,
    agent_namespace: str = "agent_support",
    _: None = Depends(require_admin),
) -> HTMLResponse:
    with get_session() as db:
        documents = db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()).limit(100)).all()
    body = "<form><input name='query' placeholder='search'><input name='agent_namespace' value='" + agent_namespace + "'><button>Search</button></form>"
    body += "<table><tr><th>ID</th><th>Title</th><th>Namespace</th><th>Source</th><th>Created</th></tr>"
    for document in documents:
        body += f"<tr><td>{document.id}</td><td>{document.title}</td><td>{document.agent_namespace}</td><td>{document.source_uri}</td><td>{document.created_at}</td></tr>"
    return _admin_page("Knowledge", body + "</table>")


def get_agent(agent_id: str):
    """Ленивая инициализация агентов."""
    if agent_id not in _agents:
        registry = {
            "pmo": PMOAgent,
            "data_analyst": DataAnalystAgent,
            "developer": DeveloperAgent,
            "copywriter": CopywriterAgent,
            "support": SupportAgent,
            "strategist": StrategistAgent,
            "accountant": AccountantAgent,
        }
        cls = registry.get(agent_id)
        if cls:
            _agents[agent_id] = cls()
    return _agents.get(agent_id)


def format_error(error: Exception) -> str:
    """Преобразовать ошибку в понятное сообщение."""
    message = str(error).strip()
    return message.strip('"') or error.__class__.__name__


async def notify_agent_completion(
    agent_id: str,
    message: str,
    response_text: str,
    task_id: str,
    *,
    routed_by_pmo: bool = False,
    title: Optional[str] = None,
) -> bool:
    """Send a Telegram notification after an agent finishes a task."""
    agent_name = AGENT_NAMES.get(agent_id, agent_id)
    notification_title = title or (
        "AI Office: PMO завершил задачу" if routed_by_pmo else "AI Office: бот завершил задачу"
    )

    return await send_telegram_message(
        f"{notification_title}\n"
        f"Исполнитель: {agent_name}\n"
        f"Task ID: {task_id}\n"
        f"Запрос: {message[:700]}\n\n"
        f"Результат:\n{response_text[:1800]}"
    )


async def run_pmo_dispatch(
    message: str,
    *,
    conversation_history: Optional[list[dict[str, object]]] = None,
    notify_telegram_enabled: bool = False,
) -> dict[str, object]:
    """PMO routes the task and returns the selected agent's user-facing answer."""
    await publish_agent_status(
        "pmo",
        "routing",
        message="PMO разбирает задачу и выбирает исполнителя",
    )
    route_task = _build_chat_prompt(message, conversation_history or [])
    pmo = get_agent("pmo")
    route_result = await pmo.process({
        "current_task": route_task,
        "messages": conversation_history or [],
        "subtasks": [],
    })

    target_agent_id = route_result.get("active_agent", "data_analyst")
    if target_agent_id == "pmo":
        target_agent_id = "data_analyst"

    await publish_agent_status(
        "pmo",
        "delegated",
        message=f"Маршрут передан: {AGENT_NAMES.get(target_agent_id, target_agent_id)}",
        handled_by=target_agent_id,
    )
    asyncio.create_task(reset_agent_status_later("pmo", delay_seconds=1.8))
    target_agent = get_agent(target_agent_id)
    if not target_agent:
        raise ValueError(f"PMO выбрал неизвестного агента: {target_agent_id}")

    result = await run_agent_text_task(
        target_agent_id,
        message,
        conversation_history=conversation_history,
    )
    response_text = result["result"]
    task_id = result["task_id"]
    telegram_sent = False
    if notify_telegram_enabled:
        telegram_sent = await notify_agent_completion(
            target_agent_id,
            message,
            response_text,
            task_id,
            routed_by_pmo=True,
        )

    return {
        "agent_id": "pmo",
        "handled_by": target_agent_id,
        "handled_by_name": AGENT_NAMES.get(target_agent_id, target_agent_id),
        "result": response_text,
        "task_id": task_id,
        "telegram_notified": telegram_sent,
        "status": "ok",
    }


async def run_agent_text_task(
    agent_id: str,
    message: str,
    *,
    conversation_history: Optional[list[dict[str, object]]] = None,
) -> dict[str, str]:
    """Run an agent for web chat and force a plain text model answer."""
    agent = get_agent(agent_id)
    if not agent:
        raise ValueError(f"Неизвестный агент: {agent_id}")

    task_id = f"web_{uuid.uuid4().hex[:8]}"
    db_task_id: int | None = None
    try:
        if should_auto_create_tables():
            init_db()
        with get_session() as db:
            task = TaskService(db).create_task(
                TaskCreate(
                    title=message.strip()[:180] or f"Telegram task for {agent_id}",
                    description=message,
                    created_by="user",
                    assigned_agent=agent_id,
                    status="running",
                    priority=3,
                )
            )
            db_task_id = task.id
            TaskService(db).add_event(
                task.id,
                TaskEventCreate(
                    event_type="telegram_task_started",
                    message="Task received from Telegram/Web runtime.",
                    metadata={"external_task_id": task_id, "agent_id": agent_id},
                ),
            )
    except Exception as error:
        logger.warning("task.persistence.start_failed", task_id=task_id, error=format_error(error))

    await publish_agent_status(
        agent_id,
        "thinking",
        message="Готовит ответ",
        task_id=task_id,
    )
    try:
        response_text = await agent.process_task(
            message,
            chat_history=conversation_history or [],
            use_tools=False,
            max_tokens=2400,
        )
    except Exception:
        if db_task_id is not None:
            try:
                with get_session() as db:
                    TaskService(db).update_status(
                        db_task_id,
                        "failed",
                        message=f"Agent failed for external task {task_id}.",
                    )
            except Exception as persist_error:
                logger.warning(
                    "task.persistence.fail_status_failed",
                    task_id=task_id,
                    error=format_error(persist_error),
                )
        await publish_agent_status(
            agent_id,
            "error",
            message="Не удалось завершить задачу",
            task_id=task_id,
        )
        asyncio.create_task(
            reset_agent_status_later(agent_id, delay_seconds=4, task_id=task_id)
        )
        raise
    response_text = str(response_text or "").strip()
    if not response_text:
        if db_task_id is not None:
            try:
                with get_session() as db:
                    TaskService(db).update_status(
                        db_task_id,
                        "failed",
                        message=f"Empty model response for external task {task_id}.",
                    )
            except Exception as persist_error:
                logger.warning(
                    "task.persistence.empty_status_failed",
                    task_id=task_id,
                    error=format_error(persist_error),
                )
        await publish_agent_status(
            agent_id,
            "error",
            message="Модель вернула пустой ответ",
            task_id=task_id,
        )
        asyncio.create_task(
            reset_agent_status_later(agent_id, delay_seconds=4, task_id=task_id)
        )
        raise RuntimeError(
            "Модель вернула пустой ответ. Попробуйте повторить запрос или проверить API-ключ модели."
        )

    if db_task_id is not None:
        try:
            with get_session() as db:
                TaskService(db).save_result(
                    db_task_id,
                    summary=response_text[:800],
                    payload={"external_task_id": task_id, "agent_id": agent_id},
                    status="completed",
                )
        except Exception as error:
            logger.warning("task.persistence.result_failed", task_id=task_id, error=format_error(error))

    await publish_agent_status(
        agent_id,
        "done",
        message="Ответ готов",
        task_id=task_id,
    )
    asyncio.create_task(reset_agent_status_later(agent_id, task_id=task_id))

    return {
        "task_id": task_id,
        "result": response_text,
    }


def _build_chat_prompt(message: str, conversation_history: list[dict[str, object]]) -> str:
    """Combine recent user context for lightweight PMO routing."""
    prior_user_turns = [
        str(item.get("text", "")).strip()
        for item in conversation_history[-8:]
        if str(item.get("role", "")).strip() == "user" and str(item.get("text", "")).strip()
    ]
    if not prior_user_turns:
        return message

    context_block = "\n".join(f"- {turn}" for turn in prior_user_turns[:-1])
    if not context_block:
        return message
    return (
        "История пользовательских сообщений:\n"
        f"{context_block}\n\n"
        f"Текущий запрос:\n{message}"
    )


def _serialize_conversation(conversation: dict[str, object]) -> dict[str, object]:
    """Normalize conversation payload for JSON responses."""
    return {
        "id": conversation.get("id"),
        "title": conversation.get("title", "Новый диалог"),
        "agent_id": conversation.get("agent_id", "pmo"),
        "created_at": conversation.get("created_at"),
        "updated_at": conversation.get("updated_at"),
        "messages": conversation.get("messages", []),
    }


def _telegram_conversation_id(chat_id: str | int) -> str:
    """Build a stable JSON filename-safe conversation id for a Telegram chat."""
    raw = str(chat_id).strip().replace("-", "m")
    return f"telegram_{raw}"


def _telegram_topic_bindings_id(chat_id: str | int) -> str:
    """Build a stable storage id for Telegram topic bindings."""
    raw = str(chat_id).strip().replace("-", "m")
    return f"telegram_topics_{raw}"


def _extract_telegram_message(update: dict[str, object]) -> dict[str, object] | None:
    """Return the user-facing message payload from a Telegram update."""
    for key in ("message", "channel_post", "edited_message", "edited_channel_post"):
        value = update.get(key)
        if isinstance(value, dict):
            return value
    return None


def _extract_telegram_callback_query(update: dict[str, object]) -> dict[str, object] | None:
    """Return Telegram callback_query payload when present."""
    value = update.get("callback_query")
    return value if isinstance(value, dict) else None


def _telegram_access_error(update: dict[str, object]) -> tuple[int, str] | None:
    """Return an HTTP error if a Telegram update is not allowlisted."""
    settings = get_settings()
    allowed_users = parse_id_allowlist(
        str(getattr(settings, "allowed_telegram_user_ids", ""))
    )
    allowed_chats = parse_id_allowlist(
        str(getattr(settings, "allowed_telegram_chat_ids", ""))
    )
    if not allowed_users:
        return 503, "Telegram whitelist is not configured."

    callback_query = _extract_telegram_callback_query(update)
    message = _extract_telegram_message(update)
    if callback_query:
        callback_message = callback_query.get("message")
        message = callback_message if isinstance(callback_message, dict) else None
        sender = callback_query.get("from")
    else:
        sender = message.get("from") if isinstance(message, dict) else None

    if not message:
        if callback_query:
            return 403, "Telegram callback chat is not allowed."
        return None

    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return 403, "Telegram chat is not allowed."
    if allowed_chats and str(chat.get("id")) not in allowed_chats:
        return 403, "Telegram chat is not allowed."

    if not isinstance(sender, dict) or sender.get("id") is None:
        return 403, "Telegram user is not allowed."
    if str(sender.get("id")) not in allowed_users:
        return 403, "Telegram user is not allowed."

    return None


async def _notify_telegram_access_error(
    update: dict[str, object],
    *,
    agent_id: str,
    reason: str,
) -> None:
    """Tell the chat why an update was ignored without exposing secrets."""
    message = _extract_telegram_message(update)
    callback_query = _extract_telegram_callback_query(update)
    if callback_query and not message:
        callback_message = callback_query.get("message")
        message = callback_message if isinstance(callback_message, dict) else None
        sender = callback_query.get("from")
    else:
        sender = message.get("from") if isinstance(message, dict) else None

    if not isinstance(message, dict):
        return
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return

    user_id = sender.get("id") if isinstance(sender, dict) else "unknown"
    chat_id = chat.get("id")
    thread_id = _telegram_message_thread_id(message)
    try:
        await send_telegram_message_to(
            chat_id,
            "AI Office ignored this message: access is not allowed.\n"
            f"Reason: {reason}\n"
            f"Your Telegram user_id: {user_id}\n"
            f"Chat id: {chat_id}\n"
            "Add this user_id to ALLOWED_TELEGRAM_USER_IDS.",
            agent_id=agent_id,
            message_thread_id=thread_id,
        )
    except Exception as error:
        logger.warning("telegram.access_notice.failed", reason=reason, error=format_error(error))


def _normalize_telegram_command(text: str) -> tuple[str | None, str]:
    """Parse Telegram slash commands while ignoring an optional bot username."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None, stripped

    command, _, rest = stripped.partition(" ")
    command = command[1:].split("@", 1)[0].lower()
    return command, rest.strip()


def _telegram_message_thread_id(message: dict[str, object]) -> int | None:
    """Extract a forum topic id from a Telegram message when present."""
    thread_id = message.get("message_thread_id")
    if isinstance(thread_id, int):
        return thread_id
    try:
        return int(str(thread_id)) if thread_id is not None else None
    except (TypeError, ValueError):
        return None


def _configured_telegram_thread_id(topic_name: str) -> int | None:
    """Return a thread id configured through env vars."""
    field_name = TELEGRAM_THREAD_FIELDS.get(topic_name)
    if not field_name:
        return None
    raw_value = str(getattr(get_settings(), field_name, "")).strip()
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError:
        logger.warning("telegram.thread.invalid", topic=topic_name, value=raw_value)
        return None


def _load_telegram_topic_bindings(chat_id: str | int) -> dict[str, int]:
    """Load topic bindings saved with /bind commands."""
    conversation = chat_store.get_conversation(_telegram_topic_bindings_id(chat_id))
    if not conversation:
        return {}
    bindings = conversation.get("topic_bindings", {})
    if not isinstance(bindings, dict):
        return {}

    parsed: dict[str, int] = {}
    for name, value in bindings.items():
        try:
            parsed[str(name)] = int(value)
        except (TypeError, ValueError):
            continue
    return parsed


def _save_telegram_topic_binding(chat_id: str | int, topic_name: str, thread_id: int) -> None:
    """Persist one Telegram topic binding for the current deployment filesystem."""
    conversation_id = _telegram_topic_bindings_id(chat_id)
    conversation = chat_store.get_conversation(conversation_id)
    if not conversation:
        conversation = chat_store.create_conversation(
            agent_id="pmo",
            title=f"Telegram topics {chat_id}",
            conversation_id=conversation_id,
        )
    bindings = conversation.setdefault("topic_bindings", {})
    if not isinstance(bindings, dict):
        bindings = {}
        conversation["topic_bindings"] = bindings
    bindings[topic_name] = thread_id
    conversation["updated_at"] = utc_now_iso()
    chat_store._write_file(conversation_id, conversation)


def _resolve_telegram_thread_id(
    chat_id: str | int,
    topic_name: str,
    *,
    fallback_thread_id: int | None = None,
) -> int | None:
    """Resolve a Telegram topic id from env, /bind storage, or current message."""
    configured_thread_id = _configured_telegram_thread_id(topic_name)
    if configured_thread_id is not None:
        return configured_thread_id
    return _load_telegram_topic_bindings(chat_id).get(topic_name, fallback_thread_id)


def _normalize_telegram_topic_name(raw_name: str) -> str | None:
    """Map Telegram /bind aliases to supported topic names."""
    key = raw_name.strip().lower()
    if key in {"general", "общий", "главный"}:
        return "general"
    return TELEGRAM_AGENT_ALIASES.get(key)


def _is_telegram_group_chat(chat: dict[str, object]) -> bool:
    """Return whether this update came from a shared Telegram chat."""
    return str(chat.get("type", "")).strip().lower() in {"group", "supergroup", "channel"}


def _should_ignore_specialist_group_update(
    *,
    default_agent_id: str,
    chat: dict[str, object],
    chat_id: str | int,
    source_thread_id: int | None,
) -> bool:
    """Keep specialist bots quiet in shared chats unless the message is in their topic."""
    if default_agent_id == "pmo" or not _is_telegram_group_chat(chat):
        return False

    bound_thread_id = _resolve_telegram_thread_id(chat_id, default_agent_id)
    if bound_thread_id is None or source_thread_id is None:
        return True
    return bound_thread_id != source_thread_id


def _should_ignore_pmo_topic_update(
    *,
    command: str | None,
    chat: dict[str, object],
    chat_id: str | int,
    source_thread_id: int | None,
) -> bool:
    """Keep PMO focused on General while specialists handle their own topics."""
    if command is not None or not _is_telegram_group_chat(chat) or source_thread_id is None:
        return False

    general_thread_id = _resolve_telegram_thread_id(chat_id, "general")
    if general_thread_id is not None:
        return source_thread_id != general_thread_id

    for specialist_id in SPECIALIST_AGENT_IDS:
        specialist_thread_id = _resolve_telegram_thread_id(chat_id, specialist_id)
        if specialist_thread_id == source_thread_id:
            return True
    return False


def _parse_telegram_agent_command(
    command: str | None,
    body: str,
    *,
    default_agent_id: str = "pmo",
) -> tuple[str, str, bool]:
    """Return agent id, task text, and whether all specialists should run."""
    if command in {"start", "help"}:
        return "help", body, False
    if command == "agents":
        return "agents", body, False
    if command in {"all", "все"}:
        return "pmo", body, True
    if command == "agent":
        alias, _, task = body.partition(" ")
        return TELEGRAM_AGENT_ALIASES.get(alias.lower(), default_agent_id), task.strip(), False
    if command:
        return TELEGRAM_AGENT_ALIASES.get(command, default_agent_id), body, False
    return default_agent_id, body, False


def _telegram_help_text() -> str:
    """Return a compact command guide for Telegram users."""
    return (
        "AI Office в Telegram готов к работе.\n\n"
        "Команды:\n"
        "/status - сводка по целям, задачам и brain\n"
        "/add_goal цель - добавить цель и создать задачи\n"
        "/goals - список целей\n"
        "/pmo задача - PMO выберет нужного агента\n"
        "/agent developer задача - прямой вызов агента\n"
        "/all задача - параллельный запуск всех специалистов\n"
        "/tasks - открытые задачи\n"
        "/daily_plan - персональный план по целям\n"
        "/plan - запустить дневное планирование\n"
        "/projects - список проектов\n"
        "/project ai-office - карточка проекта\n"
        "/memory - что бот помнит о пользователе\n"
        "/create_site запрос - создать сайт\n"
        "/create_tool запрос - создать инструмент\n"
        "/brain_status - активный brain provider\n"
        "/approve 1 или /reject 1 - решение по approval\n"
        "/autonomy status|on|off - статус автономности\n"
        "/bind developer - привязать текущую тему к агенту\n"
        "/agents - список агентов\n\n"
        "Без команды сообщение пойдет через PMO. Также можно писать естественным текстом:\n"
        "\"запомни: мой главный проект AI Office\"\n"
        "\"что ты обо мне помнишь?\"\n"
        "\"создай сайт для AI Office\""
    )


def _telegram_agents_text() -> str:
    """Return supported Telegram agent names."""
    return (
        "Агенты:\n"
        "PMO: /pmo\n"
        "Аналитик: /agent data_analyst\n"
        "Разработчик: /agent developer\n"
        "Копирайтер: /agent copywriter\n"
        "Поддержка: /agent support\n"
        "Стратег: /agent strategist\n"
        "Бухгалтер: /agent accountant"
    )


def _telegram_user_identity(message: dict[str, object]) -> tuple[str, str]:
    sender = message.get("from")
    if not isinstance(sender, dict):
        return "telegram-user", ""
    external_id = str(sender.get("id") or "telegram-user")
    display_name = " ".join(
        part.strip()
        for part in [
            str(sender.get("first_name") or ""),
            str(sender.get("last_name") or ""),
        ]
        if part.strip()
    ).strip()
    if not display_name:
        display_name = str(sender.get("username") or "")
    return external_id, display_name


def _find_project_slug_for_text(
    db,
    text: str,
    *,
    external_id: str = "",
) -> str | None:
    lowered = text.lower()
    project_service = ProjectService(db)
    projects = project_service.list_projects()
    for project in projects:
        if project.slug in lowered or project.name.lower() in lowered:
            return project.slug

    compact = slugify(text)
    if compact and compact != "project":
        project = project_service.get_project_by_slug(compact)
        if project:
            return project.slug

    profile = None
    if external_id:
        profile = ProfileMemoryService(db).ensure_profile(external_id=external_id)
    if profile and profile.primary_project_slug:
        return profile.primary_project_slug
    if projects:
        return projects[0].slug
    return None


def _brain_status_text() -> str:
    settings = get_settings()
    base_url = settings.brain_base_url.strip() or "default provider endpoint"
    return (
        "Brain configuration:\n"
        f"Provider: {settings.brain_provider}\n"
        f"Base URL: {base_url}\n"
        f"Cheap model: {settings.brain_cheap_model}\n"
        f"Strong model: {settings.brain_strong_model}\n"
        f"Code model: {settings.brain_code_model}"
    )


def _handle_change_brain_command(db, *, external_id: str, body: str) -> str:
    provider = body.strip().lower()
    if not provider:
        return (
            "Используйте: /change_brain openai|anthropic|google|openrouter|custom\n"
            "Для P2 это сохраняет предпочтение пользователя; реальное переключение идет через env и restart."
        )
    profile = ProfileMemoryService(db).ensure_profile(external_id=external_id)
    preferences = dict(profile.preferences_json or {})
    preferences["brain_provider_override"] = provider
    profile.preferences_json = preferences
    db.add(profile)
    db.commit()
    return (
        f"Сохранил brain preference: {provider}.\n"
        "Runtime-маршрутизация для демо сейчас управляется через BRAIN_* env vars."
    )


def _format_telegram_goals(db, *, external_id: str) -> str:
    engine = GoalEngineService(db)
    goals = engine.list_goals(external_id=external_id)
    if not goals:
        return "Целей пока нет. Добавьте через /add_goal Подготовить AI Office к демо"
    lines = ["Цели:"]
    for goal in goals[:8]:
        lines.append(
            f"#{goal.id} [{goal.status}] {'ON' if goal.autonomy_enabled else 'OFF'} {goal.title}"
        )
        for index, step in enumerate((goal.plan_json or [])[:3], start=1):
            lines.append(f"  {index}. {step.get('title', 'Следующий шаг')}")
    return "\n".join(lines)


def _status_summary_text(db, *, external_id: str) -> str:
    task_counts = TaskService(db).count_by_status()
    approval_counts = ApprovalService(db).count_by_status()
    goal_count = len(GoalEngineService(db).list_goals(external_id=external_id))
    site_count = len(ArtifactGenerationService(db).list_sites())
    tool_count = len(ArtifactGenerationService(db).list_tools())
    return (
        f"AI Office status\n"
        f"Goals: {goal_count}\n"
        f"Tasks open: {task_counts.get('planned', 0) + task_counts.get('queued', 0) + task_counts.get('running', 0) + task_counts.get('waiting_approval', 0)}\n"
        f"Approvals pending: {approval_counts.get('pending', 0)}\n"
        f"Generated sites: {site_count}\n"
        f"Generated tools: {tool_count}\n"
        f"Autonomy: {'ON' if get_autonomy_enabled() else 'OFF'}\n"
        f"Brain: {get_settings().brain_provider}"
    )


def _create_goal_from_telegram(
    db,
    *,
    external_id: str,
    display_name: str,
    goal_text: str,
) -> str:
    if not goal_text.strip():
        return "Укажите цель: /add_goal Подготовить AI Office к демонстрации"
    profile_memory = ProfileMemoryService(db)
    goal_engine = GoalEngineService(db)
    goal = goal_engine.add_goal(external_id=external_id, title=goal_text.strip())
    created_ids = goal_engine.create_tasks_for_goal(goal_id=goal.id)
    project_slug = _find_project_slug_for_text(db, goal_text, external_id=external_id) or slugify(goal_text)
    profile = profile_memory.ensure_profile(external_id=external_id, display_name=display_name)
    if project_slug:
        profile.primary_project_slug = project_slug
        db.add(profile)
        db.commit()
    profile_memory.remember_fact(
        external_id=external_id,
        display_name=display_name,
        text=f"Цель пользователя: {goal_text.strip()}",
        project_slug=project_slug,
    )
    return (
        f"[PMO] Цель добавлена: {goal.title}\n"
        f"[PMO] Создано задач: {len(created_ids)}\n"
        "Посмотреть: /goals и /tasks"
    )


def _create_site_from_telegram(
    db,
    *,
    prompt: str,
    external_id: str,
    display_name: str,
) -> tuple[str, dict | None]:
    request_prompt = prompt.strip()
    if not request_prompt:
        return ("Укажите запрос: /create_site сайт для AI Office", None)
    project_slug = _find_project_slug_for_text(db, request_prompt, external_id=external_id)
    service = ArtifactGenerationService(db)
    site = service.create_site(
        prompt=request_prompt,
        user_external_id=external_id,
        project_slug=project_slug or "",
    )
    ProfileMemoryService(db).remember_fact(
        external_id=external_id,
        display_name=display_name,
        text=f"Создан сайт {site.site_id} по запросу: {request_prompt}",
        project_slug=project_slug,
    )
    link = f"{get_settings().app_base_url.rstrip('/')}{site.public_path}"
    return (
        f"[Developer] Готово. Я создал сайт.\n"
        f"Site id: {site.site_id}\n"
        f"Тип: {site.site_type}\n"
        f"Ссылка: {link}",
        None,
    )


def _create_tool_from_telegram(
    db,
    *,
    prompt: str,
    external_id: str,
    display_name: str,
) -> tuple[str, dict | None]:
    request_prompt = prompt.strip()
    if not request_prompt:
        return ("Укажите запрос: /create_tool калькулятор стоимости AI Office", None)
    project_slug = _find_project_slug_for_text(db, request_prompt, external_id=external_id)
    service = ArtifactGenerationService(db)
    tool = service.create_tool(
        prompt=request_prompt,
        user_external_id=external_id,
        project_slug=project_slug or "",
    )
    ProfileMemoryService(db).remember_fact(
        external_id=external_id,
        display_name=display_name,
        text=f"Создан инструмент {tool.tool_id} по запросу: {request_prompt}",
        project_slug=project_slug,
    )
    link = f"{get_settings().app_base_url.rstrip('/')}{tool.public_path}"
    return (
        f"[Developer] Готово. Я создал инструмент.\n"
        f"Tool id: {tool.tool_id}\n"
        f"Тип: {tool.tool_type}\n"
        f"Ссылка: {link}",
        None,
    )


def _create_github_issue_approval_from_telegram(
    db,
    *,
    request_text: str,
    external_id: str,
) -> tuple[str, dict | None]:
    title = request_text.strip()
    if not title:
        title = "Создай GitHub issue с задачами на завтра"
    task = TaskService(db).create_task(
        TaskCreate(
            title=title[:180],
            input_text=title,
            description=title,
            created_by="user",
            assigned_agent="developer",
            status="waiting_approval",
            requires_approval=True,
            risk_level="medium",
        )
    )
    result = ToolExecutionService(db).call_tool(
        "github.issue.create",
        {
            "title": "AI Office demo follow-up",
            "body": request_text,
        },
        ToolContext(task_id=task.id, workspace_id="default", agent_name="developer", actor_id=external_id),
    )
    if not result.requires_approval or not result.approval_id:
        return ("GitHub action prepared without approval queue.", None)
    approval_id = int(result.approval_id)
    return (
        f"[PMO] Подготовил GitHub issue в dry-run.\n"
        f"Нужен approval #{approval_id}.\n"
        f"Approve: /approve {approval_id}\n"
        f"Reject: /reject {approval_id}",
        approval_inline_keyboard(approval_id),
    )


async def _handle_telegram_product_flow(
    *,
    text: str,
    chat_id: str | int,
    message_id: int | None,
    source_thread_id: int | None,
    default_agent_id: str,
    external_id: str,
    display_name: str,
) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False

    if not any(
        marker in lowered
        for marker in [
            "запомни:",
            "что ты обо мне помнишь",
            "что ты знаешь про",
            "что у нас по проекту",
            "что ты сам предлагаешь",
            "какие задачи ты сам предлагаешь",
            "создай сайт",
            "создай калькулятор",
            "создай инструмент",
            "создай tool",
            "создай github issue",
        ]
    ):
        return False

    response_text = ""
    reply_markup = None
    try:
        if should_auto_create_tables():
            init_db()
        with get_session() as db:
            memory = ProfileMemoryService(db)
            goals = GoalEngineService(db)
            if lowered.startswith("запомни:"):
                fact = text.split(":", 1)[1].strip()
                project_slug = _find_project_slug_for_text(db, fact, external_id=external_id)
                memory.remember_fact(
                    external_id=external_id,
                    display_name=display_name,
                    text=fact,
                    project_slug=project_slug,
                )
                response_text = f"[Memory] Запомнил.\n{fact}"
            elif "что ты обо мне помнишь" in lowered:
                response_text = memory.memory_summary(external_id=external_id)
            elif "что ты знаешь про" in lowered:
                project_slug = _find_project_slug_for_text(db, text, external_id=external_id)
                if project_slug:
                    response_text = memory.project_summary(project_slug=project_slug)
                else:
                    response_text = memory.memory_summary(external_id=external_id)
            elif "что у нас по проекту" in lowered:
                project_slug = _find_project_slug_for_text(db, text, external_id=external_id)
                response_text = _format_telegram_project(db, slug=project_slug or "")
            elif "что ты сам предлагаешь" in lowered or "какие задачи ты сам предлагаешь" in lowered:
                response_text = goals.suggest_tasks_text(external_id=external_id)
            elif lowered.startswith("создай сайт"):
                response_text, reply_markup = _create_site_from_telegram(
                    db,
                    prompt=text,
                    external_id=external_id,
                    display_name=display_name,
                )
            elif any(marker in lowered for marker in ["создай калькулятор", "создай инструмент", "создай tool"]):
                response_text, reply_markup = _create_tool_from_telegram(
                    db,
                    prompt=text,
                    external_id=external_id,
                    display_name=display_name,
                )
            elif "создай github issue" in lowered:
                response_text, reply_markup = _create_github_issue_approval_from_telegram(
                    db,
                    request_text=text,
                    external_id=external_id,
                )
    except Exception as error:
        logger.error("telegram.product_flow.error", error=str(error), exc_info=True)
        response_text = f"Команда не выполнена: {format_error(error)}"

    await send_telegram_message_to(
        chat_id,
        response_text,
        agent_id=default_agent_id,
        reply_to_message_id=message_id,
        message_thread_id=source_thread_id,
        reply_markup=reply_markup,
    )
    return True


async def _run_telegram_single_agent(
    *,
    chat_id: str | int,
    message_id: int | None,
    agent_id: str,
    task: str,
    conversation_id: str,
    response_thread_id: int | None = None,
) -> None:
    """Run one agent and send its answer back to Telegram."""
    history_for_prompt = chat_store.recent_context(conversation_id, limit=12)
    chat_store.append_message(
        conversation_id,
        ChatMessage(
            role="user",
            text=task,
            created_at=utc_now_iso(),
            agent_id=agent_id,
        ),
    )

    try:
        if agent_id == "pmo":
            result_payload = await run_pmo_dispatch(
                task,
                conversation_history=history_for_prompt,
            )
            handled_by = str(result_payload.get("handled_by", "pmo"))
        else:
            result = await run_agent_text_task(
                agent_id,
                task,
                conversation_history=history_for_prompt,
            )
            handled_by = agent_id
            result_payload = {
                "handled_by": handled_by,
                "handled_by_name": AGENT_NAMES.get(handled_by, handled_by),
                "result": result["result"],
                "task_id": result["task_id"],
            }

        response_text = str(result_payload.get("result", "")).strip()
        task_id = str(result_payload.get("task_id", ""))
        agent_name = AGENT_NAMES.get(handled_by, handled_by)
        await send_telegram_message_to(
            chat_id,
            f"{agent_name} завершил задачу\nTask: {task_id}\n\n{response_text}",
            agent_id=agent_id,
            reply_to_message_id=message_id,
            message_thread_id=response_thread_id,
        )
        chat_store.append_message(
            conversation_id,
            ChatMessage(
                role="assistant",
                text=response_text,
                created_at=utc_now_iso(),
                agent_id=agent_id,
                handled_by=handled_by,
                task_id=task_id or None,
            ),
        )
    except MissingLLMCredentialsError as error:
        await send_telegram_message_to(
            chat_id,
            format_error(error),
            agent_id=agent_id,
            reply_to_message_id=message_id,
            message_thread_id=response_thread_id,
        )
    except Exception as error:
        logger.error("telegram.agent_task.error", agent_id=agent_id, error=str(error), exc_info=True)
        await send_telegram_message_to(
            chat_id,
            f"Агент не смог завершить задачу: {format_error(error)}",
            agent_id=agent_id,
            reply_to_message_id=message_id,
            message_thread_id=response_thread_id,
        )


async def _run_telegram_pmo_routed_task(
    *,
    chat_id: str | int,
    message_id: int | None,
    task: str,
    conversation_id: str,
    source_thread_id: int | None = None,
) -> None:
    """Let PMO route a General message, then post work/results in the target topic."""
    history_for_prompt = chat_store.recent_context(conversation_id, limit=12)
    chat_store.append_message(
        conversation_id,
        ChatMessage(
            role="user",
            text=task,
            created_at=utc_now_iso(),
            agent_id="pmo",
        ),
    )

    try:
        route_task = _build_chat_prompt(task, history_for_prompt)
        pmo = get_agent("pmo")
        route_result = await pmo.process({
            "current_task": route_task,
            "messages": history_for_prompt,
            "subtasks": [],
        })

        target_agent_id = str(route_result.get("active_agent", "data_analyst"))
        if target_agent_id == "pmo":
            target_agent_id = "data_analyst"
        if target_agent_id not in AGENT_NAMES:
            target_agent_id = "data_analyst"

        target_thread_id = _resolve_telegram_thread_id(
            chat_id,
            target_agent_id,
            fallback_thread_id=source_thread_id,
        )
        target_agent_name = AGENT_NAMES.get(target_agent_id, target_agent_id)

        await send_telegram_message_to(
            chat_id,
            f"PMO направил задачу → {target_agent_name}\n\n{task}",
            agent_id="pmo",
            reply_to_message_id=message_id if target_thread_id == source_thread_id else None,
            message_thread_id=target_thread_id,
        )

        result = await run_agent_text_task(
            target_agent_id,
            task,
            conversation_history=history_for_prompt,
        )
        response_text = result["result"]
        task_id = result["task_id"]

        await send_telegram_message_to(
            chat_id,
            f"{target_agent_name} завершил задачу\nTask: {task_id}\n\n{response_text}",
            agent_id=target_agent_id,
            message_thread_id=target_thread_id,
        )
        chat_store.append_message(
            conversation_id,
            ChatMessage(
                role="assistant",
                text=response_text,
                created_at=utc_now_iso(),
                agent_id="pmo",
                handled_by=target_agent_id,
                task_id=task_id,
            ),
        )
    except MissingLLMCredentialsError as error:
        await send_telegram_message_to(
            chat_id,
            format_error(error),
            agent_id="pmo",
            reply_to_message_id=message_id,
            message_thread_id=source_thread_id,
        )
    except Exception as error:
        logger.error("telegram.pmo_routing.error", error=str(error), exc_info=True)
        await send_telegram_message_to(
            chat_id,
            f"PMO не смог маршрутизировать задачу: {format_error(error)}",
            agent_id="pmo",
            reply_to_message_id=message_id,
            message_thread_id=source_thread_id,
        )


async def _run_telegram_all_agents(
    *,
    chat_id: str | int,
    message_id: int | None,
    task: str,
    conversation_id: str,
    response_thread_id: int | None = None,
) -> None:
    """Run all specialist agents concurrently and send a compact digest."""
    history_for_prompt = chat_store.recent_context(conversation_id, limit=12)
    chat_store.append_message(
        conversation_id,
        ChatMessage(role="user", text=task, created_at=utc_now_iso(), agent_id="all"),
    )

    async def run_one(agent_id: str) -> tuple[str, str, str]:
        try:
            result = await run_agent_text_task(
                agent_id,
                task,
                conversation_history=history_for_prompt,
            )
            return agent_id, result["task_id"], result["result"]
        except Exception as error:
            logger.error("telegram.parallel_agent.error", agent_id=agent_id, error=str(error), exc_info=True)
            return agent_id, "", f"Ошибка: {format_error(error)}"

    results = await asyncio.gather(*(run_one(agent_id) for agent_id in SPECIALIST_AGENT_IDS))
    digest_parts: list[str] = []
    for agent_id, task_id, result_text in results:
        agent_name = AGENT_NAMES.get(agent_id, agent_id)
        digest_parts.append(f"{agent_name} ({task_id or 'error'}):\n{str(result_text).strip()[:900]}")

    digest = "\n\n".join(digest_parts)
    await send_telegram_message_to(
        chat_id,
        f"Параллельная работа агентов завершена\n\n{digest}",
        agent_id="pmo",
        reply_to_message_id=message_id,
        message_thread_id=response_thread_id,
    )
    chat_store.append_message(
        conversation_id,
        ChatMessage(
            role="assistant",
            text=digest,
            created_at=utc_now_iso(),
            agent_id="all",
            handled_by="all",
        ),
    )


async def _handle_telegram_runtime_command(
    *,
    command: str | None,
    body: str,
    chat_id: str | int,
    message_id: int | None,
    source_thread_id: int | None,
    default_agent_id: str,
    external_id: str = "telegram-user",
    display_name: str = "",
) -> bool:
    """Handle Telegram-first task/autonomy commands."""
    if command not in {
        "status",
        "tasks",
        "plan",
        "daily_plan",
        "project",
        "projects",
        "goals",
        "goal_status",
        "add_goal",
        "memory",
        "create_site",
        "create_tool",
        "brain_status",
        "change_brain",
        "approve",
        "reject",
        "autonomy",
        "autonomy_on",
        "autonomy_off",
    }:
        return False

    reply_markup = None
    try:
        if should_auto_create_tables():
            init_db()
        with get_session() as db:
            if command == "status":
                text = _status_summary_text(db, external_id=external_id)
            elif command == "tasks":
                text = _format_telegram_tasks(db, mode=body.strip().lower())
            elif command == "projects":
                text = _format_telegram_projects(db)
            elif command == "project":
                slug = body.strip() or (_find_project_slug_for_text(db, body, external_id=external_id) or "")
                text = _format_telegram_project(db, slug=slug)
            elif command == "plan":
                result = await AutonomyService(db).daily_plan(notify=False)
                text = result.summary
            elif command == "daily_plan":
                text = GoalEngineService(db).daily_plan_text(external_id=external_id)
            elif command in {"goals", "goal_status"}:
                text = _format_telegram_goals(db, external_id=external_id)
            elif command == "add_goal":
                text = _create_goal_from_telegram(
                    db,
                    external_id=external_id,
                    display_name=display_name,
                    goal_text=body,
                )
            elif command == "memory":
                project_slug = _find_project_slug_for_text(db, body, external_id=external_id) if body.strip() else None
                memory = ProfileMemoryService(db)
                text = (
                    memory.project_summary(project_slug=project_slug)
                    if project_slug
                    else memory.memory_summary(external_id=external_id)
                )
            elif command == "create_site":
                text, reply_markup = _create_site_from_telegram(
                    db,
                    prompt=body,
                    external_id=external_id,
                    display_name=display_name,
                )
            elif command == "create_tool":
                text, reply_markup = _create_tool_from_telegram(
                    db,
                    prompt=body,
                    external_id=external_id,
                    display_name=display_name,
                )
            elif command == "brain_status":
                text = _brain_status_text()
            elif command == "change_brain":
                text = _handle_change_brain_command(db, external_id=external_id, body=body)
            elif command == "approve":
                text = _decide_telegram_approval(db, body, approve=True)
            elif command == "reject":
                text = _decide_telegram_approval(db, body, approve=False)
            elif command == "autonomy_on":
                text = _handle_telegram_autonomy_command(db, "on")
            elif command == "autonomy_off":
                text = _handle_telegram_autonomy_command(db, "off")
            else:
                text = _handle_telegram_autonomy_command(db, body)
    except Exception as error:
        logger.error("telegram.runtime_command.error", command=command, error=str(error), exc_info=True)
        text = f"Команда не выполнена: {format_error(error)}"

    await send_telegram_message_to(
        chat_id,
        text,
        agent_id=default_agent_id,
        reply_to_message_id=message_id,
        message_thread_id=source_thread_id,
        reply_markup=reply_markup,
    )
    return True


def _format_telegram_projects(db) -> str:
    projects = ProjectService(db).list_projects()
    if not projects:
        return "Проектов пока нет. Создайте через API или запустите /plan."
    lines = ["Проекты:"]
    for project in projects[:20]:
        lines.append(
            f"{project.slug}: {project.name} [{project.status}], priority {project.priority}"
        )
    return "\n".join(lines)


def _format_telegram_tasks(db, *, mode: str = "") -> str:
    task_service = TaskService(db)
    today_only = mode == "today"
    open_only = mode in {"", "open", "today"}
    tasks = task_service.list_tasks(open_only=open_only)
    if today_only:
        today = datetime.now(timezone.utc).date()
        tasks = [task for task in tasks if task.updated_at.date() == today]
    if not tasks:
        return "Открытых задач нет." if open_only else "Задач пока нет."

    projects = {project.id: project for project in ProjectService(db).list_projects()}
    lines = ["Задачи:"]
    current_project_id: int | None = None
    for task in tasks[:30]:
        if task.project_id != current_project_id:
            current_project_id = task.project_id
            project = projects.get(task.project_id)
            lines.append(f"\n{project.name if project else 'Без проекта'}")
        lines.append(
            f"#{task.id} [{task.status}] p{task.priority} {task.assigned_agent}: {task.title}"
        )
    return "\n".join(lines).strip()


def _format_telegram_project(db, *, slug: str) -> str:
    if not slug:
        projects = ProjectService(db).list_projects()
        if not projects:
            return "Проектов пока нет. Создайте цель через /add_goal или запустите /plan."
        slug = projects[0].slug
    project_service = ProjectService(db)
    project = project_service.get_project_by_slug(slug)
    if not project:
        return f"Проект `{slug}` не найден."

    task_service = TaskService(db)
    tasks = task_service.list_tasks(project_id=project.id, open_only=True)
    lines = [
        f"{project.name} ({project.slug})",
        f"Статус: {project.status}, priority {project.priority}",
        f"Цель: {project.goal or 'не задана'}",
        "",
        "Активные задачи:",
    ]
    if tasks:
        lines.extend(
            f"#{task.id} [{task.status}] {task.assigned_agent}: {task.title}"
            for task in tasks[:10]
        )
    else:
        lines.append("Нет открытых задач. Запустите /plan, чтобы PMO предложил следующий шаг.")

    recent_events = []
    for task in tasks[:5]:
        recent_events.extend(task_service.list_events(task.id)[-2:])
    if recent_events:
        lines.extend(["", "Последние события:"])
        lines.extend(
            f"{event.event_type}: {event.message[:120]}"
            for event in sorted(recent_events, key=lambda item: item.created_at)[-5:]
        )
    return "\n".join(lines)


def _decide_telegram_approval(db, body: str, *, approve: bool) -> str:
    raw_id = body.strip().split(" ", 1)[0]
    if not raw_id.isdigit():
        return "Укажите approval id: /approve 1 или /reject 1"
    service = ApprovalService(db)
    try:
        if approve:
            approval = service.approve(int(raw_id), approved_by="telegram")
            verb = "approved"
        else:
            approval = service.reject(int(raw_id), approved_by="telegram")
            verb = "rejected"
    except ApprovalStateError as error:
        return f"Approval #{raw_id} cannot be changed: {error}"
    if not approval:
        return f"Approval #{raw_id} не найден."
    return f"Approval #{approval.id} {verb}. Связанная задача: {approval.task_id or 'нет'}."


def _handle_telegram_autonomy_command(db, body: str) -> str:
    action = body.strip().lower() or "status"
    if action == "on":
        set_autonomy_enabled(True)
        autonomy_scheduler.start()
        return "Autonomy включена. Scheduler будет выполнять безопасные циклы."
    if action == "off":
        set_autonomy_enabled(False)
        return "Autonomy выключена. Scheduler остается загруженным, но циклы не выполняет."
    if action != "status":
        return "Используйте: /autonomy status, /autonomy on, /autonomy off"

    settings = get_settings()
    task_counts = TaskService(db).count_by_status()
    approval_counts = ApprovalService(db).count_by_status()
    return (
        f"Autonomy: {'ON' if get_autonomy_enabled() else 'OFF'}\n"
        f"Scheduler: {'running' if autonomy_scheduler.running else 'stopped'}\n"
        "Tasks: "
        f"{task_counts.get('queued', 0)} queued, "
        f"{task_counts.get('running', 0)} running, "
        f"{task_counts.get('waiting_approval', 0)} waiting approval, "
        f"{task_counts.get('stuck', 0)} stuck\n"
        f"Approvals: {approval_counts.get('pending', 0)} pending, {approval_counts.get('expired', 0)} expired\n"
        f"Last daily plan: {autonomy_scheduler.last_daily_plan_run_at or 'never'}\n"
        f"Last evening review: {autonomy_scheduler.last_evening_review_run_at or 'never'}\n"
        f"DB: {'connected' if database_connected() else 'down'}\n"
        f"Poll interval: {settings.autonomy_poll_interval_seconds}s"
    )


async def _handle_telegram_callback_query(
    update: dict[str, object],
    *,
    default_agent_id: str,
) -> bool:
    """Handle Telegram inline approval callbacks."""
    callback_query = _extract_telegram_callback_query(update)
    if not callback_query:
        return False

    data = str(callback_query.get("data") or "")
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "approval" or parts[1] not in {"approve", "reject"}:
        return True

    raw_approval_id = parts[2]
    message = callback_query.get("message")
    chat = message.get("chat") if isinstance(message, dict) else None
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    message_id = message.get("message_id") if isinstance(message, dict) else None
    source_thread_id = _telegram_message_thread_id(message) if isinstance(message, dict) else None
    if chat_id is None or not raw_approval_id.isdigit():
        return True

    if should_auto_create_tables():
        init_db()
    with get_session() as db:
        text = _decide_telegram_approval(
            db,
            raw_approval_id,
            approve=parts[1] == "approve",
        )

    await send_telegram_message_to(
        chat_id,
        text,
        agent_id=default_agent_id,
        reply_to_message_id=message_id if isinstance(message_id, int) else None,
        message_thread_id=source_thread_id,
    )
    return True


async def process_telegram_update(
    update: dict[str, object],
    *,
    default_agent_id: str = "pmo",
) -> None:
    """Handle an incoming Telegram webhook update."""
    if await _handle_telegram_callback_query(update, default_agent_id=default_agent_id):
        return

    message = _extract_telegram_message(update)
    if not message:
        return

    chat = message.get("chat")
    if not isinstance(chat, dict):
        return

    text = str(message.get("text") or message.get("caption") or "").strip()
    if not text:
        return

    chat_id = chat.get("id")
    message_id = message.get("message_id")
    source_thread_id = _telegram_message_thread_id(message)
    external_id, display_name = _telegram_user_identity(message)
    if chat_id is None:
        return

    command, body = _normalize_telegram_command(text)
    if await _handle_telegram_runtime_command(
        command=command,
        body=body,
        chat_id=chat_id,
        message_id=message_id if isinstance(message_id, int) else None,
        source_thread_id=source_thread_id,
        default_agent_id=default_agent_id,
        external_id=external_id,
        display_name=display_name,
    ):
        return

    if await _handle_telegram_product_flow(
        text=text,
        chat_id=chat_id,
        message_id=message_id if isinstance(message_id, int) else None,
        source_thread_id=source_thread_id,
        default_agent_id=default_agent_id,
        external_id=external_id,
        display_name=display_name,
    ):
        return

    if command == "bind":
        if default_agent_id != "pmo":
            return
        topic_name = _normalize_telegram_topic_name(body)
        if not topic_name:
            await send_telegram_message_to(
                chat_id,
                "Укажите тему: /bind general, /bind developer, /bind data_analyst и т.д.",
                agent_id=default_agent_id,
                reply_to_message_id=message_id if isinstance(message_id, int) else None,
                message_thread_id=source_thread_id,
            )
            return
        if source_thread_id is None:
            await send_telegram_message_to(
                chat_id,
                "Эту команду нужно отправить внутри Telegram Topic, чтобы я увидел message_thread_id.",
                agent_id=default_agent_id,
                reply_to_message_id=message_id if isinstance(message_id, int) else None,
            )
            return

        _save_telegram_topic_binding(chat_id, topic_name, source_thread_id)
        await send_telegram_message_to(
            chat_id,
            f"Привязал тему `{topic_name}` к thread_id={source_thread_id}.",
            agent_id=default_agent_id,
            reply_to_message_id=message_id if isinstance(message_id, int) else None,
            message_thread_id=source_thread_id,
        )
        return

    if default_agent_id == "pmo" and _should_ignore_pmo_topic_update(
        command=command,
        chat=chat,
        chat_id=chat_id,
        source_thread_id=source_thread_id,
    ):
        return

    agent_id, task, run_all = _parse_telegram_agent_command(
        command,
        body,
        default_agent_id=default_agent_id,
    )
    if _should_ignore_specialist_group_update(
        default_agent_id=default_agent_id,
        chat=chat,
        chat_id=chat_id,
        source_thread_id=source_thread_id,
    ):
        return
    if agent_id == "help":
        if default_agent_id != "pmo" and _is_telegram_group_chat(chat):
            return
        await send_telegram_message_to(
            chat_id,
            _telegram_help_text(),
            agent_id=default_agent_id,
            reply_to_message_id=message_id,
            message_thread_id=source_thread_id,
        )
        return
    if agent_id == "agents":
        if default_agent_id != "pmo" and _is_telegram_group_chat(chat):
            return
        await send_telegram_message_to(
            chat_id,
            _telegram_agents_text(),
            agent_id=default_agent_id,
            reply_to_message_id=message_id,
            message_thread_id=source_thread_id,
        )
        return
    if not task:
        await send_telegram_message_to(
            chat_id,
            "Напишите задачу после команды. Например: /pmo подготовь план запуска",
            agent_id=default_agent_id,
            reply_to_message_id=message_id,
            message_thread_id=source_thread_id,
        )
        return

    conversation_id = _telegram_conversation_id(chat_id)
    if not chat_store.get_conversation(conversation_id):
        chat_store.create_conversation(
            agent_id=agent_id,
            title=f"Telegram {chat_id}",
            conversation_id=conversation_id,
        )
    chat_store.touch_conversation(conversation_id, agent_id=agent_id)

    await send_telegram_message_to(
        chat_id,
        "Принял задачу. Запускаю агентов.",
        agent_id=agent_id,
        reply_to_message_id=message_id,
        message_thread_id=source_thread_id,
    )
    if run_all:
        await _run_telegram_all_agents(
            chat_id=chat_id,
            message_id=message_id if isinstance(message_id, int) else None,
            task=task,
            conversation_id=conversation_id,
            response_thread_id=source_thread_id,
        )
        return

    target_thread_id = _resolve_telegram_thread_id(
        chat_id,
        agent_id,
        fallback_thread_id=source_thread_id,
    )
    if agent_id == "pmo":
        await _run_telegram_pmo_routed_task(
            chat_id=chat_id,
            message_id=message_id if isinstance(message_id, int) else None,
            task=task,
            conversation_id=conversation_id,
            source_thread_id=source_thread_id,
        )
        return

    await _run_telegram_single_agent(
        chat_id=chat_id,
        message_id=message_id if isinstance(message_id, int) else None,
        agent_id=agent_id,
        task=task,
        conversation_id=conversation_id,
        response_thread_id=target_thread_id,
    )


@app.get("/health")
async def health():
    """Health check для хостинга и load balancer."""
    settings = get_settings()
    database_ok = database_connected()
    telegram_configured = telegram_runtime_configured()
    return {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
        "scheduler": autonomy_scheduler.running,
        "autonomy_enabled": get_autonomy_enabled(),
        "telegram_configured": telegram_configured,
        "model_keys": {
            "openai": bool(settings.openai_api_key.strip()),
            "anthropic": bool(settings.anthropic_api_key.strip()),
            "google": bool(settings.google_api_key.strip()),
        },
    }


@app.get("/api/cron/autonomy-tick")
async def autonomy_cron_tick(request: Request):
    """Run autonomous polling from Vercel Cron instead of relying on a warm process."""
    settings = get_settings()
    expected = settings.cron_secret.strip()
    if not expected:
        return JSONResponse({"error": "CRON_SECRET is not configured"}, status_code=503)

    actual = request.headers.get("Authorization", "")
    if not hmac.compare_digest(actual, f"Bearer {expected}"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    if not get_autonomy_enabled():
        return {
            "status": "skipped",
            "reason": "autonomy_disabled",
            "autonomy_enabled": False,
        }

    if should_auto_create_tables():
        init_db()
    try:
        with get_session() as db:
            audit_log(
                db,
                workspace_id="default",
                actor_type="system",
                actor_id="cron",
                action="cron.autonomy_tick_requested",
                object_type="scheduler",
                object_id="autonomy_tick",
                metadata={"source": "http", "secret_present": bool(expected)},
                commit=True,
            )
    except Exception as error:
        logger.warning("cron.audit.failed", error=format_error(error))

    tz = ZoneInfo(settings.autonomy_timezone)
    now = datetime.now(tz)
    job_results = await autonomy_scheduler.tick_once(
        notify=True,
        now=now.astimezone(timezone.utc),
    )
    results_by_job = {item.job_key: item for item in job_results}
    poll_result = (results_by_job.get("autonomous_tick") or type("Result", (), {"result_json": None})()).result_json
    daily_plan = (results_by_job.get("daily_plan") or type("Result", (), {"result_json": None})()).result_json
    evening_review = (results_by_job.get("evening_review") or type("Result", (), {"result_json": None})()).result_json

    return {
        "status": "ok",
        "autonomy_enabled": True,
        "now": now.isoformat(timespec="seconds"),
        "poll": poll_result or {"completed": [], "waiting_approval": [], "failed": []},
        "daily_plan": daily_plan,
        "evening_review": evening_review,
    }


# ── Главная страница ─────────────────────────────────────────────────
def _build_dashboard_context(agents_list: list[dict[str, str]], settings) -> dict[str, object]:
    """Collect a small read-only dashboard snapshot without exposing secrets."""
    database_ok = database_connected()
    telegram_configured = telegram_runtime_configured()
    agent_status_map = {
        str(item.get("agent_id") or item.get("id")): item
        for item in get_agent_statuses()
    }
    agents = []
    for agent in agents_list:
        status = agent_status_map.get(agent["id"], {})
        agents.append({
            **agent,
            "status": str(status.get("status") or "idle"),
            "message": str(status.get("message") or "Свободен"),
            "task_id": str(status.get("task_id") or ""),
        })

    task_counts: dict[str, int] = {}
    approval_counts: dict[str, int] = {}
    projects: list[dict[str, object]] = []
    open_tasks: list[dict[str, object]] = []
    recent_tasks: list[dict[str, object]] = []
    pending_approvals: list[dict[str, object]] = []
    goals: list[dict[str, object]] = []
    sites: list[dict[str, object]] = []
    tools: list[dict[str, object]] = []
    recent_memory: list[dict[str, object]] = []
    db_error = ""

    if database_ok:
        try:
            with get_session() as db:
                task_service = TaskService(db)
                approval_service = ApprovalService(db)
                project_service = ProjectService(db)
                task_counts = task_service.count_by_status()
                approval_counts = approval_service.count_by_status()
                projects = [
                    {
                        "slug": project.slug,
                        "name": project.name,
                        "status": project.status,
                        "priority": project.priority,
                        "goal": project.goal,
                    }
                    for project in project_service.list_projects()[:8]
                ]
                open_tasks = [
                    {
                        "id": task.id,
                        "title": task.title,
                        "status": task.status,
                        "priority": task.priority,
                        "assigned_agent": task.assigned_agent,
                        "project": task.project.slug if task.project else "none",
                        "requires_approval": task.requires_approval,
                    }
                    for task in task_service.list_tasks(open_only=True)[:12]
                ]
                recent_tasks = [
                    {
                        "id": task.id,
                        "title": task.title,
                        "status": task.status,
                        "priority": task.priority,
                        "assigned_agent": task.assigned_agent,
                        "project": task.project.slug if task.project else "telegram",
                        "updated_at": task.updated_at.strftime("%Y-%m-%d %H:%M"),
                        "result_summary": (task.result_summary or "")[:220],
                    }
                    for task in task_service.list_tasks()[:12]
                ]
                pending_approvals = [
                    {
                        "id": approval.id,
                        "action_type": approval.action_type,
                        "summary": approval.summary,
                        "task_id": approval.task_id,
                        "requested_by_agent": approval.requested_by_agent,
                    }
                    for approval in approval_service.list_approvals(status="pending")[:8]
                ]
                goals = [
                    {
                        "id": goal.id,
                        "title": goal.title,
                        "status": goal.status,
                        "autonomy_enabled": goal.autonomy_enabled,
                        "plan_preview": [step.get("title", "Следующий шаг") for step in (goal.plan_json or [])[:3]],
                    }
                    for goal in db.scalars(select(Goal).order_by(Goal.updated_at.desc()).limit(6))
                ]
                sites = [
                    {
                        "site_id": site.site_id,
                        "title": site.title,
                        "site_type": site.site_type,
                        "public_path": site.public_path,
                    }
                    for site in db.scalars(select(GeneratedSite).order_by(GeneratedSite.created_at.desc()).limit(6))
                ]
                tools = [
                    {
                        "tool_id": tool.tool_id,
                        "title": tool.title,
                        "tool_type": tool.tool_type,
                        "public_path": tool.public_path,
                    }
                    for tool in db.scalars(select(GeneratedTool).order_by(GeneratedTool.created_at.desc()).limit(6))
                ]
                recent_memory = [
                    {
                        "kind": memory.kind,
                        "content": memory.content[:180],
                        "created_at": memory.created_at.strftime("%Y-%m-%d %H:%M"),
                    }
                    for memory in db.scalars(select(Memory).order_by(Memory.created_at.desc()).limit(6))
                ]
        except Exception as error:
            db_error = format_error(error)

    for status in ["planned", "queued", "running", "waiting_approval", "completed", "failed", "cancelled", "stuck"]:
        task_counts.setdefault(status, 0)
    approval_counts.setdefault("pending", 0)

    telegram_commands = [
        "/status",
        "/add_goal",
        "/goals",
        "/tasks",
        "/tasks today",
        "/daily_plan",
        "/plan",
        "/memory",
        "/projects",
        "/project ai-office",
        "/create_site",
        "/create_tool",
        "/brain_status",
        "/approve <id>",
        "/reject <id>",
        "/autonomy status",
    ]

    return {
        "agents": agents,
        "database_ok": database_ok,
        "database_error": db_error,
        "telegram_configured": telegram_configured,
        "autonomy_enabled": get_autonomy_enabled(),
        "scheduler_running": autonomy_scheduler.running,
        "task_counts": task_counts,
        "approval_counts": approval_counts,
        "projects": projects,
        "open_tasks": open_tasks,
        "recent_tasks": recent_tasks,
        "pending_approvals": pending_approvals,
        "goals": goals,
        "sites": sites,
        "tools": tools,
        "recent_memory": recent_memory,
        "telegram_commands": telegram_commands,
        "poll_interval_seconds": settings.autonomy_poll_interval_seconds,
        "daily_plan_hour": settings.autonomy_daily_plan_hour,
        "evening_review_hour": settings.autonomy_evening_review_hour,
        "timezone": settings.autonomy_timezone,
        "last_daily_plan_run_at": autonomy_scheduler.last_daily_plan_run_at or "never",
        "last_evening_review_run_at": autonomy_scheduler.last_evening_review_run_at or "never",
        "last_poll_run_at": autonomy_scheduler.last_poll_run_at or "never",
        "model_keys": {
            "OpenAI": bool(settings.openai_api_key.strip()),
            "Anthropic": bool(settings.anthropic_api_key.strip()),
            "Google": bool(settings.google_api_key.strip()),
        },
        "brain_status": {
            "provider": settings.brain_provider,
            "cheap_model": settings.brain_cheap_model,
            "strong_model": settings.brain_strong_model,
            "code_model": settings.brain_code_model,
        },
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, _: None = Depends(require_admin)):
    """Read-only operating dashboard. Agent work stays in Telegram/API."""
    agents_list = [
        {"id": "pmo", "name": "PMO", "role": "Оркестратор задач"},
        {"id": "data_analyst", "name": "Аналитик", "role": "Данные и метрики"},
        {"id": "developer", "name": "Разработчик", "role": "Код и ревью"},
        {"id": "copywriter", "name": "Копирайтер", "role": "Контент и документы"},
        {"id": "support", "name": "Поддержка", "role": "Тикеты и FAQ"},
        {"id": "strategist", "name": "Стратег", "role": "Рынок и roadmap"},
        {"id": "accountant", "name": "Бухгалтер", "role": "Финансы и документы"},
    ]
    settings = get_settings()
    dashboard = _build_dashboard_context(agents_list, settings)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=dashboard,
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, _: None = Depends(require_admin)):
    return await index(request)


@app.get("/agents")
async def agents_page(_: None = Depends(require_admin)) -> HTMLResponse:
    dashboard = _build_dashboard_context(
        [
            {"id": "pmo", "name": "PMO", "role": "Оркестратор задач"},
            {"id": "data_analyst", "name": "Аналитик", "role": "Данные и метрики"},
            {"id": "developer", "name": "Разработчик", "role": "Код и артефакты"},
            {"id": "copywriter", "name": "Копирайтер", "role": "Контент и документы"},
            {"id": "support", "name": "Поддержка", "role": "Knowledge ответы"},
            {"id": "strategist", "name": "Стратег", "role": "Рынок и roadmap"},
            {"id": "accountant", "name": "Бухгалтер", "role": "Финансы и документы"},
        ],
        get_settings(),
    )
    body = "<div class='grid cards'>"
    for agent in dashboard["agents"]:
        body += (
            "<div class='card'>"
            f"<div class='pill'>{html.escape(agent['status'])}</div>"
            f"<h3>{html.escape(agent['name'])}</h3>"
            f"<p>{html.escape(agent['role'])}</p>"
            f"<p class='muted'>{html.escape(agent['message'])}</p>"
            "</div>"
        )
    body += "</div>"
    return _product_page("Agents", body, subtitle="Живой список сотрудников и их последнего статуса.")


@app.get("/goals")
async def goals_page(_: None = Depends(require_admin)) -> HTMLResponse:
    with get_session() as db:
        goals = list(db.scalars(select(Goal).order_by(Goal.updated_at.desc()).limit(50)))
    if not goals:
        body = "<div class='panel'>Целей пока нет. Добавьте первую через Telegram: <code>/add_goal Подготовить AI Office к демонстрации</code>.</div>"
        return _product_page("Goals", body, subtitle="Goal engine и автономный backlog.")

    body = "<div class='list'>"
    for goal in goals:
        plan_preview = "".join(
            f"<p>{index}. {html.escape(step.get('title', 'Следующий шаг'))}</p>"
            for index, step in enumerate((goal.plan_json or [])[:5], start=1)
        )
        body += (
            "<div class='row'>"
            f"<strong>#{goal.id} {html.escape(goal.title)}</strong>"
            f"<p>{html.escape(goal.status)} · autonomy {'on' if goal.autonomy_enabled else 'off'}</p>"
            f"{plan_preview or '<p>План пока пуст.</p>'}"
            "</div>"
        )
    body += "</div>"
    return _product_page("Goals", body, subtitle="Цели пользователя и предложенные системой шаги.")


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(_: None = Depends(require_admin)) -> HTMLResponse:
    with get_session() as db:
        tasks = TaskService(db).list_tasks()[:100]
    rows = "".join(
        "<tr>"
        f"<td>#{task.id}</td>"
        f"<td>{html.escape(task.title)}</td>"
        f"<td>{html.escape(task.status)}</td>"
        f"<td>{html.escape(task.assigned_agent)}</td>"
        f"<td>{html.escape(task.project.slug if task.project else 'none')}</td>"
        f"<td>{task.updated_at.strftime('%Y-%m-%d %H:%M')}</td>"
        "</tr>"
        for task in tasks
    )
    body = (
        "<div class='panel'><table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Agent</th><th>Project</th><th>Updated</th></tr></thead>"
        f"<tbody>{rows or '<tr><td colspan=6>Задач пока нет.</td></tr>'}</tbody></table></div>"
    )
    return _product_page("Tasks", body, subtitle="Общая очередь работы и execution history.")


@app.get("/sites", response_class=HTMLResponse)
async def sites_page(_: None = Depends(require_admin)) -> HTMLResponse:
    with get_session() as db:
        sites = ArtifactGenerationService(db).list_sites()
    if not sites:
        body = "<div class='panel'>Сайтов пока нет. Создайте через <code>/create_site сайт для AI Office</code>.</div>"
        return _product_page("Sites", body, subtitle="Сгенерированные сайты, доступные прямо из браузера.")
    body = "<div class='list'>"
    for site in sites:
        body += (
            "<div class='row'>"
            f"<strong>{html.escape(site.title)}</strong>"
            f"<p>{html.escape(site.site_id)} · {html.escape(site.site_type)}</p>"
            f"<p><a href='{html.escape(site.public_path)}'>{html.escape(site.public_path)}</a></p>"
            "</div>"
        )
    body += "</div>"
    return _product_page("Sites", body, subtitle="Generated sites stored under generated_sites/.")


@app.get("/tools", response_class=HTMLResponse)
async def tools_page(_: None = Depends(require_admin)) -> HTMLResponse:
    with get_session() as db:
        tools = ArtifactGenerationService(db).list_tools()
    if not tools:
        body = "<div class='panel'>Инструментов пока нет. Создайте через <code>/create_tool калькулятор стоимости AI Office</code>.</div>"
        return _product_page("Tools", body, subtitle="Интерактивные инструменты для демо и продаж.")
    body = "<div class='list'>"
    for tool in tools:
        body += (
            "<div class='row'>"
            f"<strong>{html.escape(tool.title)}</strong>"
            f"<p>{html.escape(tool.tool_id)} · {html.escape(tool.tool_type)}</p>"
            f"<p><a href='{html.escape(tool.public_path)}'>{html.escape(tool.public_path)}</a></p>"
            "</div>"
        )
    body += "</div>"
    return _product_page("Tools", body, subtitle="Generated tools stored under generated_tools/.")


@app.get("/memory", response_class=HTMLResponse)
async def memory_page(_: None = Depends(require_admin)) -> HTMLResponse:
    with get_session() as db:
        profiles = list(db.scalars(select(UserProfile).order_by(UserProfile.updated_at.desc()).limit(10)))
        memories = list(db.scalars(select(Memory).order_by(Memory.created_at.desc()).limit(40)))
    body = "<div class='grid cards'>"
    for profile in profiles:
        body += (
            "<div class='card'>"
            f"<h3>{html.escape(profile.display_name or profile.external_id)}</h3>"
            f"<p>external_id: {html.escape(profile.external_id)}</p>"
            f"<p class='muted'>primary project: {html.escape(profile.primary_project_slug or 'not set')}</p>"
            f"<p class='muted'>style: {html.escape(profile.communication_style or 'not set')}</p>"
            "</div>"
        )
    body += "</div>"
    body += "<div class='panel'><h3>Recent Memory</h3><div class='list'>"
    for memory in memories:
        body += (
            "<div class='row'>"
            f"<strong>{html.escape(memory.kind)}</strong>"
            f"<p>{html.escape(memory.content)}</p>"
            f"<p>{memory.created_at.strftime('%Y-%m-%d %H:%M')}</p>"
            "</div>"
        )
    body += "</div></div>"
    return _product_page("Memory", body, subtitle="Профили пользователя, стиль общения и project memory.")


@app.get("/landing", response_class=HTMLResponse)
async def landing_page() -> HTMLResponse:
    body = (
        "<div class='panel'>"
        "<div class='grid cards'>"
        "<div class='card'><h3>AI Office 24/7</h3><p>Telegram-first AI office with goals, memory, approvals and autonomous planning.</p></div>"
        "<div class='card'><h3>Как работает</h3><p>Пользователь пишет в Telegram, PMO маршрутизирует работу, Developer создает сайты/tools, Support отвечает по knowledge, Memory хранит контекст.</p></div>"
        "<div class='card'><h3>Demo flow</h3><p>Добавить цель → получить backlog → создать сайт → создать калькулятор → одобрить GitHub action.</p></div>"
        "</div></div>"
        "<div class='panel'><h3>Ключевые возможности</h3><div class='list'>"
        "<div class='row'><strong>Telegram Product Bot</strong><p>Обычный чат, команды, inline approve/reject, ответы по ролям.</p></div>"
        "<div class='row'><strong>Goal Engine</strong><p>Цели, дневной план, автономные next steps, task backlog.</p></div>"
        "<div class='row'><strong>Generated Sites & Tools</strong><p>Готовые HTML/CSS/JS артефакты по команде из Telegram.</p></div>"
        "<div class='row'><strong>Bring Your Own Brain</strong><p>Конфигурируемые BRAIN_* provider/model settings для демо и пилота.</p></div>"
        "</div></div>"
        "<div class='panel'><p><a href='/dashboard'>Open live dashboard</a> · <a href='/sites'>Browse generated sites</a> · <a href='/tools'>Browse generated tools</a></p></div>"
    )
    return _product_page("AI Office 24/7", body, subtitle="Демонстрационный landing page продукта внутри самого репозитория.")


def _resolve_artifact_path(base_directory: str, asset_path: str) -> Path | None:
    base = Path(base_directory).resolve()
    target = (base / asset_path).resolve()
    if target != base and base not in target.parents:
        return None
    if not target.exists() or not target.is_file():
        return None
    return target


@app.get("/sites/{site_id}")
async def site_entry(site_id: str):
    return RedirectResponse(url=f"/sites/{site_id}/", status_code=307)


@app.get("/sites/{site_id}/")
async def site_index(site_id: str):
    with get_session() as db:
        site = ArtifactGenerationService(db).get_site(site_id)
    if not site:
        return HTMLResponse("Site not found", status_code=404)
    return FileResponse(Path(site.directory_path) / "index.html")


@app.get("/sites/{site_id}/{asset_path:path}")
async def site_asset(site_id: str, asset_path: str):
    with get_session() as db:
        site = ArtifactGenerationService(db).get_site(site_id)
    if not site:
        return HTMLResponse("Site not found", status_code=404)
    asset = _resolve_artifact_path(site.directory_path, asset_path)
    if not asset:
        return HTMLResponse("Asset not found", status_code=404)
    return FileResponse(asset)


@app.get("/tools/{tool_id}")
async def tool_entry(tool_id: str):
    return RedirectResponse(url=f"/tools/{tool_id}/", status_code=307)


@app.get("/tools/{tool_id}/")
async def tool_index(tool_id: str):
    with get_session() as db:
        tool = ArtifactGenerationService(db).get_tool(tool_id)
    if not tool:
        return HTMLResponse("Tool not found", status_code=404)
    return FileResponse(Path(tool.directory_path) / "index.html")


@app.get("/tools/{tool_id}/{asset_path:path}")
async def tool_asset(tool_id: str, asset_path: str):
    with get_session() as db:
        tool = ArtifactGenerationService(db).get_tool(tool_id)
    if not tool:
        return HTMLResponse("Tool not found", status_code=404)
    asset = _resolve_artifact_path(tool.directory_path, asset_path)
    if not asset:
        return HTMLResponse("Asset not found", status_code=404)
    return FileResponse(asset)


@app.get("/simulator", response_class=HTMLResponse)
async def simulator(request: Request):
    """Deprecated old demo UI; the web surface is now the operations dashboard."""
    return RedirectResponse(url="/", status_code=307)


@app.get("/pixel-office", response_class=HTMLResponse)
async def pixel_office(request: Request):
    """Deprecated old demo UI; the web surface is now the operations dashboard."""
    return RedirectResponse(url="/", status_code=307)


@app.get("/api/agent-events")
async def agent_events(_: None = Depends(require_api_key)):
    """Stream live agent state changes for the pixel office."""
    async def event_stream():
        async for event in subscribe_agent_events():
            yield format_sse(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/agent-statuses")
async def agent_statuses(_: None = Depends(require_api_key)):
    """Return the latest status snapshot for all office agents."""
    return JSONResponse({
        "agents": get_agent_statuses(),
        "status": "ok",
    })


@app.post("/api/telegram/notify")
async def telegram_notify(request: Request, _: None = Depends(require_admin)):
    """Send a Telegram notification from UI-only flows such as the simulator."""
    data = await request.json()
    task = data.get("task", "").strip() or "Симулятор AI Office"
    agent_id = data.get("agent_id", "pmo")
    result = data.get("result", "").strip() or "Задача завершена в симуляторе."
    task_id = data.get("task_id", "").strip() or "simulator"

    telegram_sent = await notify_agent_completion(
        agent_id,
        task,
        result,
        task_id,
        title="AI Office: симулятор завершил задачу",
    )

    return JSONResponse({
        "telegram_notified": telegram_sent,
        "status": "ok" if telegram_sent else "error",
    })


@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive Telegram Bot API updates and run AI Office agents."""
    settings = get_settings()
    expected_secret = settings.telegram_webhook_secret.strip()
    if not expected_secret:
        return JSONResponse({"error": "Telegram webhook secret is not configured"}, status_code=503)
    actual_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if actual_secret != expected_secret:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    update = await request.json()
    access_error = _telegram_access_error(update)
    if access_error:
        _, message = access_error
        logger.warning("telegram.update.ignored", reason=message)
        await _notify_telegram_access_error(update, agent_id="pmo", reason=message)
        return JSONResponse({"status": "ignored", "reason": message})
    background_tasks.add_task(process_telegram_update, update)
    return JSONResponse({"status": "accepted"})


@app.post("/api/telegram/webhook/{agent_id}")
async def telegram_agent_webhook(
    agent_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive Telegram updates for a specific agent bot."""
    if agent_id not in AGENT_NAMES:
        return JSONResponse({"error": f"Unknown agent: {agent_id}"}, status_code=404)

    settings = get_settings()
    expected_secret = settings.telegram_webhook_secret.strip()
    if not expected_secret:
        return JSONResponse({"error": "Telegram webhook secret is not configured"}, status_code=503)
    actual_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if actual_secret != expected_secret:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    update = await request.json()
    access_error = _telegram_access_error(update)
    if access_error:
        _, message = access_error
        logger.warning("telegram.update.ignored", reason=message, agent_id=agent_id)
        await _notify_telegram_access_error(update, agent_id=agent_id, reason=message)
        return JSONResponse({"status": "ignored", "reason": message, "agent_id": agent_id})
    background_tasks.add_task(
        process_telegram_update,
        update,
        default_agent_id=agent_id,
    )
    return JSONResponse({"status": "accepted", "agent_id": agent_id})


# ── API: отправка сообщения агенту ───────────────────────────────────
@app.post("/api/chat")
async def chat(request: Request, _: None = Depends(require_api_key)):
    """Отправить сообщение агенту."""
    data = await request.json()
    agent_id = data.get("agent_id", "pmo")
    message = data.get("message", "").strip()
    conversation_id = str(data.get("conversation_id", "")).strip()
    notify_telegram_enabled = bool(data.get("notify_telegram", False))

    if not message:
        return JSONResponse({"error": "Пустое сообщение"}, status_code=400)

    if not conversation_id:
        conversation = chat_store.create_conversation(agent_id=agent_id)
        conversation_id = str(conversation["id"])

    conversation = chat_store.get_conversation(conversation_id)
    if not conversation:
        return JSONResponse({"error": "Диалог не найден"}, status_code=404)

    chat_store.touch_conversation(conversation_id, agent_id=agent_id)
    agent = get_agent(agent_id)
    if not agent:
        return JSONResponse({"error": f"Неизвестный агент: {agent_id}"}, status_code=404)

    history_for_prompt = chat_store.recent_context(conversation_id, limit=12)
    chat_store.append_message(
        conversation_id,
        ChatMessage(
            role="user",
            text=message,
            created_at=utc_now_iso(),
        ),
    )

    logger.info("web.chat", agent_id=agent_id, message=message[:100])

    try:
        if agent_id == "pmo":
            result_payload = await run_pmo_dispatch(
                    message,
                    conversation_history=history_for_prompt,
                    notify_telegram_enabled=notify_telegram_enabled,
                )
            handled_by = str(result_payload.get("handled_by", "pmo"))
        else:
            result = await run_agent_text_task(
                agent_id,
                message,
                conversation_history=history_for_prompt,
            )
            response_text = result["result"]
            task_id = result["task_id"]
            telegram_sent = False
            if notify_telegram_enabled:
                telegram_sent = await notify_agent_completion(
                    agent_id,
                    message,
                    response_text,
                    task_id,
                )

            result_payload = {
                "agent_id": agent_id,
                "handled_by": agent_id,
                "handled_by_name": AGENT_NAMES.get(agent_id, agent_id),
                "result": response_text,
                "task_id": task_id,
                "telegram_notified": telegram_sent,
                "status": "ok",
            }
            handled_by = agent_id

        chat_store.append_message(
            conversation_id,
            ChatMessage(
                role="assistant",
                text=str(result_payload.get("result", "")),
                created_at=utc_now_iso(),
                agent_id=agent_id,
                handled_by=handled_by,
                task_id=str(result_payload.get("task_id", "")) or None,
            )
        )
        updated_conversation = chat_store.get_conversation(conversation_id)
        return JSONResponse({
            **result_payload,
            "conversation_id": conversation_id,
            "conversation": _serialize_conversation(updated_conversation or conversation),
        })
    except MissingLLMCredentialsError as e:
        error_message = format_error(e)
        logger.error("web.chat.config_error", agent_id=agent_id, error=error_message)
        return JSONResponse({
            "error": error_message,
            "status": "error",
        }, status_code=400)
    except Exception as e:
        error_message = format_error(e)
        logger.error("web.chat.error", agent_id=agent_id, error=error_message, exc_info=True)
        return JSONResponse({
            "error": error_message,
            "status": "error",
        }, status_code=500)


@app.get("/api/conversations")
async def list_conversations(_: None = Depends(require_api_key)):
    """Return recent conversations for the web UI."""
    return JSONResponse({
        "conversations": chat_store.list_conversations(),
        "status": "ok",
    })


@app.post("/api/conversations")
async def create_conversation(request: Request, _: None = Depends(require_api_key)):
    """Create a new empty conversation."""
    data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    agent_id = str(data.get("agent_id", "pmo")).strip() or "pmo"
    conversation = chat_store.create_conversation(agent_id=agent_id)
    return JSONResponse({
        "conversation": _serialize_conversation(conversation),
        "status": "ok",
    })


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, _: None = Depends(require_api_key)):
    """Load a conversation with all messages."""
    conversation = chat_store.get_conversation(conversation_id)
    if not conversation:
        return JSONResponse({"error": "Диалог не найден"}, status_code=404)
    return JSONResponse({
        "conversation": _serialize_conversation(conversation),
        "status": "ok",
    })


# ── API: маршрутизация через PMO ─────────────────────────────────────
@app.post("/api/route")
async def route_task(request: Request, _: None = Depends(require_api_key)):
    """PMO декомпозирует задачу и определяет маршрут."""
    data = await request.json()
    task = data.get("task", "").strip()

    if not task:
        return JSONResponse({"error": "Пустая задача"}, status_code=400)

    agent = get_agent("pmo")
    result = await agent.process({
        "current_task": task,
        "messages": [],
        "subtasks": [],
    })

    subtasks = result.get("subtasks", [])
    next_agent = result.get("active_agent", "data_analyst")

    return JSONResponse({
        "next_agent": next_agent,
        "subtasks": subtasks,
        "status": "ok",
    })


# ── API: статус агентов ──────────────────────────────────────────────
@app.get("/api/agents")
async def list_agents(_: None = Depends(require_api_key)):
    """Список всех агентов и их статус."""
    agents_info = []
    for agent_id in ["pmo", "data_analyst", "developer", "copywriter", "support", "strategist", "accountant"]:
        try:
            agent = get_agent(agent_id)
            if agent:
                model_name = "Unknown"
                try:
                    model_name = agent.get_model().__class__.__name__
                except:
                    pass
                agents_info.append({
                    "id": agent_id,
                    "model": model_name,
                    "tools": [t.name for t in agent.tools] if agent.tools else [],
                    "prompt_loaded": len(agent.system_prompt) > 0 if agent.system_prompt else False,
                })
        except Exception as e:
            logger.error("agent_load_error", agent_id=agent_id, error=str(e))
    return JSONResponse({"agents": agents_info})
