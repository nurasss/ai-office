"""FastAPI веб-интерфейс для AI Office."""

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from tenacity import RetryError
from typing import Optional

from agents import (
    AccountantAgent,
    CopywriterAgent,
    DataAnalystAgent,
    DeveloperAgent,
    PMOAgent,
    StrategistAgent,
    SupportAgent,
)
from core.llm_router import MissingLLMCredentialsError
from core.logger import get_logger, setup_logging
from tools.external.telegram import send_telegram_message

load_dotenv()
setup_logging("INFO")
logger = get_logger("web")

app = FastAPI(title="AI Office", version="1.0.0")
templates = Jinja2Templates(directory="templates")

# ── Кэш агентов (lazy init) ──────────────────────────────────────────
_agents: dict[str, object] = {}

AGENT_NAMES = {
    "pmo": "PMO",
    "data_analyst": "Аналитик",
    "developer": "Разработчик",
    "copywriter": "Копирайтер",
    "support": "Поддержка",
    "strategist": "Стратег",
    "accountant": "Бухгалтер",
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
    """Раскрыть RetryError и вернуть понятную пользователю причину."""
    if isinstance(error, RetryError):
        last_error = error.last_attempt.exception()
        if last_error:
            return format_error(last_error)

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


async def run_pmo_dispatch(message: str) -> dict[str, object]:
    """PMO routes the task and returns the selected agent's user-facing answer."""
    pmo = get_agent("pmo")
    route_result = await pmo.process({
        "current_task": message,
        "messages": [],
        "subtasks": [],
    })

    target_agent_id = route_result.get("active_agent", "data_analyst")
    if target_agent_id == "pmo":
        target_agent_id = "data_analyst"

    target_agent = get_agent(target_agent_id)
    if not target_agent:
        raise ValueError(f"PMO выбрал неизвестного агента: {target_agent_id}")

    result = await target_agent.invoke(message)
    response_text = result.get("result", "")
    task_id = result.get("task_id", "")
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
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"agents": agents_list},
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


# ── API: отправка сообщения агенту ───────────────────────────────────
@app.post("/api/chat")
async def chat(request: Request):
    """Отправить сообщение агенту."""
    data = await request.json()
    agent_id = data.get("agent_id", "pmo")
    message = data.get("message", "").strip()

    if not message:
        return JSONResponse({"error": "Пустое сообщение"}, status_code=400)

    agent = get_agent(agent_id)
    if not agent:
        return JSONResponse({"error": f"Неизвестный агент: {agent_id}"}, status_code=404)

    logger.info("web.chat", agent_id=agent_id, message=message[:100])

    try:
        if agent_id == "pmo":
            return JSONResponse(await run_pmo_dispatch(message))

        result = await agent.invoke(message)
        response_text = result.get("result", "")
        task_id = result.get("task_id", "")
        telegram_sent = await notify_agent_completion(
            agent_id,
            message,
            response_text,
            task_id,
        )

        return JSONResponse({
            "agent_id": agent_id,
            "handled_by": agent_id,
            "handled_by_name": AGENT_NAMES.get(agent_id, agent_id),
            "result": response_text,
            "task_id": task_id,
            "telegram_notified": telegram_sent,
            "status": "ok",
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
