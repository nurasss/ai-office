from fastapi.testclient import TestClient

import web.app as web_app
from core.chat_history import ChatHistoryStore
from core.config import get_settings


class FakeAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def process_task(self, message: str, **kwargs):
        self.calls.append({
            "message": message,
            **kwargs,
        })
        return f"echo:{message}"


def auth_headers(monkeypatch):
    monkeypatch.setenv("AI_OFFICE_API_KEY", "test-key")
    get_settings.cache_clear()
    return {"X-API-Key": "test-key"}


def test_chat_history_is_persisted_and_loaded(tmp_path, monkeypatch):
    headers = auth_headers(monkeypatch)
    store = ChatHistoryStore(tmp_path)
    fake_agent = FakeAgent()

    monkeypatch.setattr(web_app, "chat_store", store)
    monkeypatch.setattr(web_app, "_agents", {"copywriter": fake_agent})

    client = TestClient(web_app.app)

    create_response = client.post("/api/conversations", json={"agent_id": "copywriter"}, headers=headers)
    assert create_response.status_code == 200
    conversation_id = create_response.json()["conversation"]["id"]

    first_reply = client.post(
        "/api/chat",
        json={
            "agent_id": "copywriter",
            "conversation_id": conversation_id,
            "message": "Первый вопрос",
        },
        headers=headers,
    )
    assert first_reply.status_code == 200
    first_body = first_reply.json()
    assert first_body["conversation"]["messages"][0]["text"] == "Первый вопрос"
    assert first_body["conversation"]["messages"][1]["text"] == "echo:Первый вопрос"

    second_reply = client.post(
        "/api/chat",
        json={
            "agent_id": "copywriter",
            "conversation_id": conversation_id,
            "message": "Второй вопрос",
        },
        headers=headers,
    )
    assert second_reply.status_code == 200
    second_body = second_reply.json()
    assert len(second_body["conversation"]["messages"]) == 4

    open_response = client.get(f"/api/conversations/{conversation_id}", headers=headers)
    assert open_response.status_code == 200
    opened = open_response.json()["conversation"]
    assert opened["messages"][-1]["text"] == "echo:Второй вопрос"


def test_second_message_receives_previous_chat_history(tmp_path, monkeypatch):
    headers = auth_headers(monkeypatch)
    store = ChatHistoryStore(tmp_path)
    fake_agent = FakeAgent()

    monkeypatch.setattr(web_app, "chat_store", store)
    monkeypatch.setattr(web_app, "_agents", {"copywriter": fake_agent})

    client = TestClient(web_app.app)

    conversation_id = client.post(
        "/api/conversations",
        json={"agent_id": "copywriter"},
        headers=headers,
    ).json()["conversation"]["id"]

    client.post(
        "/api/chat",
        json={
            "agent_id": "copywriter",
            "conversation_id": conversation_id,
            "message": "Первый вопрос",
        },
        headers=headers,
    )
    client.post(
        "/api/chat",
        json={
            "agent_id": "copywriter",
            "conversation_id": conversation_id,
            "message": "Второй вопрос",
        },
        headers=headers,
    )

    assert len(fake_agent.calls) == 2
    assert fake_agent.calls[0]["chat_history"] == []
    history = fake_agent.calls[1]["chat_history"]
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["text"] == "Первый вопрос"
    assert history[1]["role"] == "assistant"
