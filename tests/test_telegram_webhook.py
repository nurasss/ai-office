from __future__ import annotations

from fastapi.testclient import TestClient

import web.app as web_app
from core.chat_history import ChatHistoryStore


class FakeSettings:
    telegram_webhook_secret = ""
    telegram_general_thread_id = ""
    telegram_pmo_thread_id = ""
    telegram_data_analyst_thread_id = ""
    telegram_developer_thread_id = ""
    telegram_copywriter_thread_id = ""
    telegram_support_thread_id = ""
    telegram_strategist_thread_id = ""
    telegram_accountant_thread_id = ""


class FakeAgent:
    async def process_task(self, message: str, **kwargs):
        return f"done:{message}"


class FakePMOAgent:
    def __init__(self, active_agent: str = "developer"):
        self.active_agent = active_agent

    async def process(self, payload):
        return {"active_agent": self.active_agent, "subtasks": []}


def telegram_update(
    text: str,
    chat_id: int = 123,
    message_id: int = 7,
    message_thread_id: int | None = None,
    chat_type: str = "group",
):
    message = {
        "message_id": message_id,
        "chat": {"id": chat_id, "type": chat_type},
        "text": text,
    }
    if message_thread_id is not None:
        message["message_thread_id"] = message_thread_id
    return {
        "update_id": 1,
        "message": message,
    }


def test_telegram_webhook_accepts_update(tmp_path, monkeypatch):
    sent_messages: list[tuple[str, str]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append((str(chat_id), text))
        return True

    monkeypatch.setattr(web_app, "chat_store", ChatHistoryStore(tmp_path))
    monkeypatch.setattr(web_app, "_agents", {"copywriter": FakeAgent()})
    monkeypatch.setattr(web_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post("/api/telegram/webhook", json=telegram_update("/agent copywriter привет"))

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert any("Принял задачу" in text for _, text in sent_messages)
    assert any("done:привет" in text for _, text in sent_messages)


def test_agent_webhook_uses_agent_as_default(tmp_path, monkeypatch):
    sent_messages: list[tuple[str, str]] = []
    fake_agent = FakeAgent()

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append((str(chat_id), text))
        return True

    monkeypatch.setattr(web_app, "chat_store", ChatHistoryStore(tmp_path))
    monkeypatch.setattr(web_app, "_agents", {"developer": fake_agent})
    monkeypatch.setattr(web_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook/developer",
        json=telegram_update("проверь код", chat_type="private"),
    )

    assert response.status_code == 200
    assert response.json()["agent_id"] == "developer"
    assert any("done:проверь код" in text for _, text in sent_messages)


def test_specialist_group_webhook_ignores_unbound_general_message(tmp_path, monkeypatch):
    sent_messages: list[tuple[str, str]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append((str(chat_id), text))
        return True

    monkeypatch.setattr(web_app, "chat_store", ChatHistoryStore(tmp_path))
    monkeypatch.setattr(web_app, "_agents", {"developer": FakeAgent()})
    monkeypatch.setattr(web_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook/developer",
        json=telegram_update("проверь код"),
    )

    assert response.status_code == 200
    assert response.json()["agent_id"] == "developer"
    assert sent_messages == []


def test_specialist_group_webhook_accepts_own_topic(tmp_path, monkeypatch):
    class TopicSettings(FakeSettings):
        telegram_developer_thread_id = "42"

    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": str(chat_id), "text": text, **kwargs})
        return True

    monkeypatch.setattr(web_app, "chat_store", ChatHistoryStore(tmp_path))
    monkeypatch.setattr(web_app, "_agents", {"developer": FakeAgent()})
    monkeypatch.setattr(web_app, "get_settings", lambda: TopicSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook/developer",
        json=telegram_update("проверь код", message_thread_id=42),
    )

    assert response.status_code == 200
    assert any("done:проверь код" in str(message["text"]) for message in sent_messages)


def test_pmo_routes_general_message_to_agent_topic(tmp_path, monkeypatch):
    class TopicSettings(FakeSettings):
        telegram_developer_thread_id = "42"

    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": str(chat_id), "text": text, **kwargs})
        return True

    monkeypatch.setattr(web_app, "chat_store", ChatHistoryStore(tmp_path))
    monkeypatch.setattr(
        web_app,
        "_agents",
        {"pmo": FakePMOAgent("developer"), "developer": FakeAgent()},
    )
    monkeypatch.setattr(web_app, "get_settings", lambda: TopicSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post("/api/telegram/webhook", json=telegram_update("проверь код"))

    assert response.status_code == 200
    assert any(
        "PMO направил задачу" in str(message["text"])
        and message.get("message_thread_id") == 42
        for message in sent_messages
    )
    assert any(
        "done:проверь код" in str(message["text"])
        and message.get("message_thread_id") == 42
        for message in sent_messages
    )


def test_pmo_ignores_specialist_topic_plain_message(tmp_path, monkeypatch):
    class TopicSettings(FakeSettings):
        telegram_general_thread_id = "1"
        telegram_developer_thread_id = "42"

    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": str(chat_id), "text": text, **kwargs})
        return True

    monkeypatch.setattr(web_app, "chat_store", ChatHistoryStore(tmp_path))
    monkeypatch.setattr(
        web_app,
        "_agents",
        {"pmo": FakePMOAgent("developer"), "developer": FakeAgent()},
    )
    monkeypatch.setattr(web_app, "get_settings", lambda: TopicSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook/pmo",
        json=telegram_update("проверь код", message_thread_id=42),
    )

    assert response.status_code == 200
    assert sent_messages == []


def test_bind_command_saves_current_topic(tmp_path, monkeypatch):
    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": str(chat_id), "text": text, **kwargs})
        return True

    store = ChatHistoryStore(tmp_path)
    monkeypatch.setattr(web_app, "chat_store", store)
    monkeypatch.setattr(web_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_update("/bind developer", message_thread_id=55),
    )

    assert response.status_code == 200
    assert web_app._load_telegram_topic_bindings(123)["developer"] == 55
    assert any("Привязал тему" in str(message["text"]) for message in sent_messages)


def test_telegram_webhook_rejects_wrong_secret(monkeypatch):
    class SecretSettings:
        telegram_webhook_secret = "expected"

    monkeypatch.setattr(web_app, "get_settings", lambda: SecretSettings())

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_update("/pmo задача"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )

    assert response.status_code == 401


def test_parse_telegram_agent_commands():
    assert web_app._parse_telegram_agent_command("pmo", "задача") == ("pmo", "задача", False)
    assert web_app._parse_telegram_agent_command("all", "задача") == ("pmo", "задача", True)
    assert web_app._parse_telegram_agent_command("agent", "developer задача") == (
        "developer",
        "задача",
        False,
    )
    assert web_app._parse_telegram_agent_command(
        None,
        "задача",
        default_agent_id="developer",
    ) == ("developer", "задача", False)
