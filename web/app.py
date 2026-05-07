"""FastAPI веб-интерфейс для AI Office."""

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from tenacity import RetryError

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

load_dotenv()
setup_logging("INFO")
logger = get_logger("web")

app = FastAPI(title="AI Office", version="1.0.0")
templates = Jinja2Templates(directory="templates")

# ── Кэш агентов (lazy init) ──────────────────────────────────────────
_agents: dict[str, object] = {}


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
        result = await agent.invoke(message)
        return JSONResponse({
            "agent_id": agent_id,
            "result": result.get("result", ""),
            "task_id": result.get("task_id", ""),
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
