from fastapi.testclient import TestClient

import web.app as web_app
from core.chat_history import ChatHistoryStore


class FakeSettings:
    telegram_webhook_secret = ""


class FakeAgent:
    async def process_task(self, message: str, **kwargs):
        return f"done:{message}"


def telegram_update(text: str, chat_id: int = 123, message_id: int = 7):
    return {
        "update_id": 1,
        "message": {
            "message_id": message_id,
            "chat": {"id": chat_id, "type": "group"},
            "text": text,
        },
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
        json=telegram_update("проверь код"),
    )

    assert response.status_code == 200
    assert response.json()["agent_id"] == "developer"
    assert any("done:проверь код" in text for _, text in sent_messages)


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
