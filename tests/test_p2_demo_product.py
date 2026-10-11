from __future__ import annotations

from fastapi.testclient import TestClient

import web.app as web_app
from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from services.artifact_generation_service import ArtifactGenerationService
from services.goal_engine_service import GoalEngineService
from services.profile_memory_service import ProfileMemoryService


def telegram_update(
    text: str,
    *,
    chat_id: int = 123,
    user_id: int = 456,
    message_id: int = 7,
    chat_type: str = "private",
):
    return {
        "update_id": 1,
        "message": {
            "message_id": message_id,
            "chat": {"id": chat_id, "type": chat_type},
            "from": {"id": user_id, "is_bot": False, "first_name": "Nuras"},
            "text": text,
        },
    }


def _configure_p2_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p2.db'}")
    monkeypatch.setenv("AI_OFFICE_REQUIRE_API_KEY", "false")
    monkeypatch.setenv("AI_OFFICE_ADMIN_TOKEN", "admin-test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("ALLOWED_TELEGRAM_USER_IDS", "456")
    monkeypatch.setenv("ALLOWED_TELEGRAM_CHAT_IDS", "123")
    monkeypatch.setenv("GENERATED_SITES_ROOT", str(tmp_path / "generated_sites"))
    monkeypatch.setenv("GENERATED_TOOLS_ROOT", str(tmp_path / "generated_tools"))
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("BRAIN_PROVIDER", "openrouter")
    monkeypatch.setenv("BRAIN_BASE_URL", "https://openrouter.example/api")
    monkeypatch.setenv("BRAIN_CHEAP_MODEL", "demo-cheap")
    monkeypatch.setenv("BRAIN_STRONG_MODEL", "demo-strong")
    monkeypatch.setenv("BRAIN_CODE_MODEL", "demo-code")
    monkeypatch.setenv("GITHUB_OWNER", "owner")
    monkeypatch.setenv("GITHUB_REPO", "repo")
    monkeypatch.setenv("ENABLE_REAL_TOOLS", "false")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()


def test_artifact_generation_service_creates_site_and_tool_assets(tmp_path, monkeypatch):
    _configure_p2_env(tmp_path, monkeypatch)

    with get_session() as db:
        service = ArtifactGenerationService(db)
        site = service.create_site(prompt="AI Office landing for investors", user_external_id="456")
        tool = service.create_tool(prompt="калькулятор стоимости AI Office", user_external_id="456")
        site_id = site.site_id
        tool_id = tool.tool_id
        site_public_path = site.public_path
        tool_public_path = tool.public_path

    assert site_id.startswith("site-")
    assert tool_id.startswith("tool-")
    assert (tmp_path / "generated_sites" / site_id / "index.html").exists()
    assert (tmp_path / "generated_tools" / tool_id / "script.js").exists()
    assert site_public_path == f"/sites/{site_id}"
    assert tool_public_path == f"/tools/{tool_id}"


def test_dashboard_and_generated_artifact_pages_render(tmp_path, monkeypatch):
    _configure_p2_env(tmp_path, monkeypatch)

    with get_session() as db:
        goal = GoalEngineService(db).add_goal(
            external_id="456",
            title="Подготовить AI Office к демонстрации",
        )
        GoalEngineService(db).create_tasks_for_goal(goal_id=goal.id, project_slug="ai-office")
        ProfileMemoryService(db).remember_fact(
            external_id="456",
            display_name="Nuras",
            text="Мой главный проект сейчас AI Office",
            project_slug="ai-office",
        )
        site = ArtifactGenerationService(db).create_site(
            prompt="AI Office landing for investors",
            user_external_id="456",
            project_slug="ai-office",
        )
        tool = ArtifactGenerationService(db).create_tool(
            prompt="AI Office cost calculator",
            user_external_id="456",
            project_slug="ai-office",
        )
        site_id = site.site_id
        tool_id = tool.tool_id
        site_public_path = site.public_path
        tool_public_path = tool.public_path

    client = TestClient(web_app.app)
    admin_headers = {"Authorization": "Bearer admin-test-token"}

    assert client.get("/dashboard").status_code == 401
    dashboard_response = client.get("/dashboard", headers=admin_headers)
    assert dashboard_response.status_code == 200
    assert "Operations Dashboard" in dashboard_response.text
    assert "Цели" in dashboard_response.text
    goals_response = client.get("/goals", headers=admin_headers)
    assert goals_response.status_code == 200
    assert "Подготовить AI Office к демонстрации" in goals_response.text
    sites_response = client.get("/sites", headers=admin_headers)
    assert sites_response.status_code == 200
    assert site_id in sites_response.text
    tools_response = client.get("/tools", headers=admin_headers)
    assert tools_response.status_code == 200
    assert tool_id in tools_response.text
    memory_response = client.get("/memory", headers=admin_headers)
    assert memory_response.status_code == 200
    assert "AI Office" in memory_response.text
    site_response = client.get(site_public_path + "/")
    assert site_response.status_code == 200
    assert "AI Office landing for investors" in site_response.text
    tool_response = client.get(tool_public_path + "/")
    assert tool_response.status_code == 200
    assert "AI Office cost calculator" in tool_response.text


def test_telegram_product_bot_flows_for_goals_memory_generation_and_github(tmp_path, monkeypatch):
    _configure_p2_env(tmp_path, monkeypatch)
    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": chat_id, "text": text, **kwargs})
        return True

    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)

    for text in [
        "/add_goal Подготовить AI Office к демонстрации",
        "/goals",
        "запомни: мой главный проект сейчас AI Office",
        "что ты обо мне помнишь?",
        "/create_site сайт для AI Office",
        "/create_tool калькулятор стоимости AI Office",
        "создай GitHub issue с задачами на завтра",
        "/brain_status",
    ]:
        response = client.post(
            "/api/telegram/webhook",
            json=telegram_update(text),
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        )
        assert response.status_code == 200

    message_texts = [str(item["text"]) for item in sent_messages]
    assert any("Цель добавлена" in text for text in message_texts)
    assert any("Цели:" in text for text in message_texts)
    assert any("Запомнил" in text for text in message_texts)
    assert any("Память о пользователе" in text for text in message_texts)
    assert any("Я создал сайт" in text and "/sites/" in text for text in message_texts)
    assert any("Я создал инструмент" in text and "/tools/" in text for text in message_texts)
    assert any("Нужен approval" in text for text in message_texts)
    assert any("Brain configuration" in text and "openrouter" in text for text in message_texts)
    assert any(item.get("reply_markup") for item in sent_messages if "approval" in str(item["text"]).lower())
