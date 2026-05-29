"""FastAPI веб-интерфейс для AI Office."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

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
from core.auth import parse_id_allowlist, require_api_key
from core.chat_history import ChatHistoryStore, ChatMessage, utc_now_iso
from core.config import get_settings
from core.db import database_connected, get_session, init_db
from core.llm_router import MissingLLMCredentialsError
from core.logger import get_logger, setup_logging
from core.schemas import TaskCreate, TaskEventCreate
from api.autonomous import router as autonomous_router
from services.approval_service import ApprovalService, ApprovalStateError
from services.autonomy_service import AutonomyService, get_autonomy_enabled, set_autonomy_enabled
from services.project_service import ProjectService
from services.scheduler import autonomy_scheduler
from services.task_service import TaskService
from tools.external.telegram import (
    send_telegram_message,
    send_telegram_message_to,
    telegram_runtime_configured,
)

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
        init_db()
    except Exception as error:
        logger.error("db.init.failed", error=str(error), exc_info=True)

    if get_autonomy_enabled():
        autonomy_scheduler.start()


@app.on_event("shutdown")
async def shutdown_autonomous_runtime() -> None:
    """Stop the in-process scheduler cleanly on shutdown."""
    await autonomy_scheduler.stop()


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
        "/pmo задача - PMO выберет нужного агента\n"
        "/agent developer задача - прямой вызов агента\n"
        "/all задача - параллельный запуск всех специалистов\n"
        "/tasks - открытые задачи\n"
        "/plan - запустить дневное планирование\n"
        "/projects - список проектов\n"
        "/project ai-office - карточка проекта\n"
        "/approve 1 или /reject 1 - решение по approval\n"
        "/autonomy status|on|off - статус автономности\n"
        "/bind developer - привязать текущую тему к агенту\n"
        "/agents - список агентов\n\n"
        "Без команды сообщение пойдет через PMO. В группе с Topics PMO может "
        "перенаправлять работу в темы агентов."
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
) -> bool:
    """Handle Telegram-first task/autonomy commands."""
    if command not in {
        "tasks",
        "plan",
        "project",
        "projects",
        "approve",
        "reject",
        "autonomy",
    }:
        return False

    try:
        init_db()
        with get_session() as db:
            if command == "tasks":
                text = _format_telegram_tasks(db, mode=body.strip().lower())
            elif command == "projects":
                text = _format_telegram_projects(db)
            elif command == "project":
                text = _format_telegram_project(db, slug=body.strip())
            elif command == "plan":
                result = await AutonomyService(db).daily_plan(notify=False)
                text = result.summary
            elif command == "approve":
                text = _decide_telegram_approval(db, body, approve=True)
            elif command == "reject":
                text = _decide_telegram_approval(db, body, approve=False)
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
        return "Укажите проект: /project ai-office"
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
        except Exception as error:
            db_error = format_error(error)

    for status in ["planned", "queued", "running", "waiting_approval", "completed", "failed", "cancelled", "stuck"]:
        task_counts.setdefault(status, 0)
    approval_counts.setdefault("pending", 0)

    telegram_commands = [
        "/tasks",
        "/tasks today",
        "/plan",
        "/projects",
        "/project ai-office",
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
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
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
async def telegram_notify(request: Request, _: None = Depends(require_api_key)):
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
