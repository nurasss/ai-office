"""FastAPI веб-интерфейс для AI Office."""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
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
from core.chat_history import ChatHistoryStore, ChatMessage, utc_now_iso
from core.config import get_settings
from core.llm_router import MissingLLMCredentialsError
from core.logger import get_logger, setup_logging
from tools.external.telegram import send_telegram_message, send_telegram_message_to

load_dotenv()
setup_logging("INFO")
logger = get_logger("web")

app = FastAPI(title="AI Office", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
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
    response_text = await agent.process_task(
        message,
        chat_history=conversation_history or [],
        use_tools=False,
        max_tokens=2400,
    )
    response_text = str(response_text or "").strip()
    if not response_text:
        raise RuntimeError(
            "Модель вернула пустой ответ. Попробуйте повторить запрос или проверить API-ключ модели."
        )

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


async def process_telegram_update(
    update: dict[str, object],
    *,
    default_agent_id: str = "pmo",
) -> None:
    """Handle an incoming Telegram webhook update."""
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
    if command == "bind":
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

    agent_id, task, run_all = _parse_telegram_agent_command(
        command,
        body,
        default_agent_id=default_agent_id,
    )
    if agent_id == "help":
        await send_telegram_message_to(
            chat_id,
            _telegram_help_text(),
            agent_id=default_agent_id,
            reply_to_message_id=message_id,
            message_thread_id=source_thread_id,
        )
        return
    if agent_id == "agents":
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
    return {"status": "ok"}


# ── Главная страница ─────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница с чатом."""
    agents_list = [
        {"id": "pmo", "name": "PMO", "icon": "📋", "desc": "Оркестратор задач"},
        {"id": "data_analyst", "name": "Аналитик", "icon": "📊", "desc": "Данные и метрики"},
        {"id": "developer", "name": "Разработчик", "icon": "💻", "desc": "Код и ревью"},
        {"id": "copywriter", "name": "Копирайтер", "icon": "✍️", "desc": "Контент"},
        {"id": "support", "name": "Поддержка", "icon": "🎧", "desc": "Техподдержка"},
        {"id": "strategist", "name": "Стратег", "icon": "🎯", "desc": "Анализ рынка"},
        {"id": "accountant", "name": "Бухгалтер", "icon": "🧮", "desc": "Финансы"},
    ]
    conversations = chat_store.list_conversations()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"agents": agents_list, "conversations": conversations},
    )


@app.get("/simulator", response_class=HTMLResponse)
async def simulator(request: Request):
    """Интерактивная демонстрация цикла LangGraph."""
    return templates.TemplateResponse(
        request=request,
        name="simulator.html",
        context={},
    )


@app.post("/api/telegram/notify")
async def telegram_notify(request: Request):
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
    if expected_secret:
        actual_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if actual_secret != expected_secret:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

    update = await request.json()
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
    if expected_secret:
        actual_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if actual_secret != expected_secret:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

    update = await request.json()
    background_tasks.add_task(
        process_telegram_update,
        update,
        default_agent_id=agent_id,
    )
    return JSONResponse({"status": "accepted", "agent_id": agent_id})


# ── API: отправка сообщения агенту ───────────────────────────────────
@app.post("/api/chat")
async def chat(request: Request):
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
async def list_conversations():
    """Return recent conversations for the web UI."""
    return JSONResponse({
        "conversations": chat_store.list_conversations(),
        "status": "ok",
    })


@app.post("/api/conversations")
async def create_conversation(request: Request):
    """Create a new empty conversation."""
    data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    agent_id = str(data.get("agent_id", "pmo")).strip() or "pmo"
    conversation = chat_store.create_conversation(agent_id=agent_id)
    return JSONResponse({
        "conversation": _serialize_conversation(conversation),
        "status": "ok",
    })


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
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
async def route_task(request: Request):
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
async def list_agents():
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
