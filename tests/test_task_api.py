from fastapi.testclient import TestClient

import web.app as web_app
from core.config import get_settings
from core.db import init_db, reset_db_engine


def test_task_api_creates_pending_task_and_lists_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("AI_OFFICE_REQUIRE_API_KEY", "false")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    client = TestClient(web_app.app)

    response = client.post(
        "/api/tasks",
        json={"title": "API task", "input_text": "Plan safely", "workspace_id": "default"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == str(body["id"])
    assert body["status"] == "pending"

    audit = client.get(f"/api/tasks/{body['id']}/audit")
    assert audit.status_code == 200
    assert any(event["action"] in {"task.created", "task.enqueued"} for event in audit.json())
