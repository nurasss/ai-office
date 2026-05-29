from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

import web.app as web_app
from core.chat_history import ChatHistoryStore
from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from core.models import utc_now
from core.schemas import ApprovalCreate, ProjectCreate, TaskCreate
from services.approval_service import ApprovalService
from services.project_service import ProjectService
from services.task_service import TaskService


class FakeSettings:
    telegram_webhook_secret = "secret"
    allowed_telegram_user_ids = "456"
    allowed_telegram_chat_ids = "123"
    telegram_general_thread_id = ""
    telegram_pmo_thread_id = ""
    telegram_data_analyst_thread_id = ""
    telegram_developer_thread_id = ""
    telegram_copywriter_thread_id = ""
    telegram_support_thread_id = ""
    telegram_strategist_thread_id = ""
    telegram_accountant_thread_id = ""
    autonomy_enabled = False
    autonomy_poll_interval_seconds = 1800
    telegram_bot_token = ""
    telegram_chat_id = ""
    openai_api_key = ""
    anthropic_api_key = ""
    google_api_key = ""


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
        "from": {"id": 456, "is_bot": False, "first_name": "Owner"},
        "text": text,
    }
    if message_thread_id is not None:
        message["message_thread_id"] = message_thread_id
    return {
        "update_id": 1,
        "message": message,
    }


def telegram_callback_update(
    data: str,
    chat_id: int = 123,
    user_id: int = 456,
    message_id: int = 9,
):
    return {
        "update_id": 2,
        "callback_query": {
            "id": "callback-id",
            "from": {"id": user_id, "is_bot": False, "first_name": "Owner"},
            "message": {
                "message_id": message_id,
                "chat": {"id": chat_id, "type": "group"},
            },
            "data": data,
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
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_update("/agent copywriter привет"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

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
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
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
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
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
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
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
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_update("проверь код"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

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
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
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
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert response.status_code == 200
    assert web_app._load_telegram_topic_bindings(123)["developer"] == 55
    assert any("Привязал тему" in str(message["text"]) for message in sent_messages)


def test_tasks_command_shows_open_tasks(tmp_path, monkeypatch):
    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": str(chat_id), "text": text, **kwargs})
        return True

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'telegram.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    with get_session() as db:
        project = ProjectService(db).create_project(
            ProjectCreate(slug="ai-office", name="AI Office")
        )
        TaskService(db).create_task(
            TaskCreate(
                project_id=project.id,
                title="Finish autonomous runtime",
                status="queued",
                assigned_agent="developer",
            )
        )

    monkeypatch.setattr(web_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_update("/tasks"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert response.status_code == 200
    assert any("Finish autonomous runtime" in str(message["text"]) for message in sent_messages)


def test_autonomy_status_command_shows_runtime_summary(tmp_path, monkeypatch):
    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": str(chat_id), "text": text, **kwargs})
        return True

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'status.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    with get_session() as db:
        TaskService(db).create_task(TaskCreate(title="Queued task", status="queued"))

    monkeypatch.setattr(web_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_update("/autonomy status"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert response.status_code == 200
    assert any("Autonomy:" in str(message["text"]) and "1 queued" in str(message["text"]) for message in sent_messages)


def test_inline_callback_approve_works_for_allowed_user(tmp_path, monkeypatch):
    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": str(chat_id), "text": text, **kwargs})
        return True

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'callback.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Needs approval", status="waiting_approval"))
        approval = ApprovalService(db).create_approval(
            ApprovalCreate(task_id=task.id, action_type="run_task", summary="Needs approval")
        )
        approval_id = approval.id

    monkeypatch.setattr(web_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_callback_update(f"approval:approve:{approval_id}"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert response.status_code == 200
    with get_session() as db:
        approval = ApprovalService(db).get_approval(approval_id)
        assert approval is not None
        assert approval.status == "approved"
    assert any("approved" in str(message["text"]) for message in sent_messages)


def test_inline_callback_reject_works_for_allowed_user(tmp_path, monkeypatch):
    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": str(chat_id), "text": text, **kwargs})
        return True

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'callback_reject.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Needs rejection", status="waiting_approval"))
        approval = ApprovalService(db).create_approval(
            ApprovalCreate(task_id=task.id, action_type="run_task", summary="Needs rejection")
        )
        approval_id = approval.id

    monkeypatch.setattr(web_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_callback_update(f"approval:reject:{approval_id}"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert response.status_code == 200
    with get_session() as db:
        approval = ApprovalService(db).get_approval(approval_id)
        assert approval is not None
        assert approval.status == "rejected"
    assert any("rejected" in str(message["text"]) for message in sent_messages)


def test_inline_callback_rejects_unauthorized_user(monkeypatch):
    class SecretSettings(FakeSettings):
        allowed_telegram_user_ids = "456"

    monkeypatch.setattr(web_app, "get_settings", lambda: SecretSettings())
    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_callback_update("approval:approve:1", user_id=999),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_inline_callback_cannot_approve_expired_approval(tmp_path, monkeypatch):
    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": str(chat_id), "text": text, **kwargs})
        return True

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'callback_expired.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Expired approval", status="waiting_approval"))
        approval = ApprovalService(db).create_approval(
            ApprovalCreate(task_id=task.id, action_type="run_task", summary="Expired approval")
        )
        approval.created_at = utc_now() - timedelta(hours=25)
        db.commit()
        approval_id = approval.id

    monkeypatch.setattr(web_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_callback_update(f"approval:approve:{approval_id}"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert response.status_code == 200
    with get_session() as db:
        approval = ApprovalService(db).get_approval(approval_id)
        assert approval is not None
        assert approval.status == "expired"
    assert any("cannot be changed" in str(message["text"]) for message in sent_messages)


def test_slash_approve_still_works(tmp_path, monkeypatch):
    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": str(chat_id), "text": text, **kwargs})
        return True

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'slash_approval.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    with get_session() as db:
        task = TaskService(db).create_task(TaskCreate(title="Slash approval", status="waiting_approval"))
        approval = ApprovalService(db).create_approval(
            ApprovalCreate(task_id=task.id, action_type="run_task", summary="Slash approval")
        )
        approval_id = approval.id

    monkeypatch.setattr(web_app, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_update(f"/approve {approval_id}"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert response.status_code == 200
    assert any("approved" in str(message["text"]) for message in sent_messages)


def test_telegram_webhook_rejects_wrong_secret(monkeypatch):
    class SecretSettings:
        telegram_webhook_secret = "expected"
        allowed_telegram_user_ids = "456"
        allowed_telegram_chat_ids = "123"

    monkeypatch.setattr(web_app, "get_settings", lambda: SecretSettings())

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_update("/pmo задача"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )

    assert response.status_code == 401


def test_telegram_webhook_rejects_missing_secret(monkeypatch):
    class SecretSettings(FakeSettings):
        telegram_webhook_secret = ""

    monkeypatch.setattr(web_app, "get_settings", lambda: SecretSettings())

    client = TestClient(web_app.app)
    response = client.post("/api/telegram/webhook", json=telegram_update("/pmo задача"))

    assert response.status_code == 503


def test_telegram_webhook_rejects_wrong_user(monkeypatch):
    class SecretSettings(FakeSettings):
        allowed_telegram_user_ids = "999"

    monkeypatch.setattr(web_app, "get_settings", lambda: SecretSettings())

    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_update("/pmo задача"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_telegram_webhook_allows_any_chat_when_chat_whitelist_empty(monkeypatch):
    class UserOnlySettings(FakeSettings):
        allowed_telegram_chat_ids = ""

    sent_messages: list[dict[str, object]] = []

    async def fake_send(chat_id, text, **kwargs):
        sent_messages.append({"chat_id": chat_id, "text": text, **kwargs})
        return True

    monkeypatch.setattr(web_app, "get_settings", lambda: UserOnlySettings())
    monkeypatch.setattr(web_app, "send_telegram_message_to", fake_send)
    client = TestClient(web_app.app)
    response = client.post(
        "/api/telegram/webhook",
        json=telegram_update("/help", chat_id=-100987654321),
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert sent_messages


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
