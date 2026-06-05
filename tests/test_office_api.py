from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import office as office_api
from api.office import router
from core.config import get_settings
from agents.pmo.pmo_agent import _route_task_by_rules
from core.state import AgentRole


def auth_headers(monkeypatch):
    monkeypatch.setenv("AI_OFFICE_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("AI_OFFICE_API_KEY", "test-key")
    get_settings.cache_clear()
    return {"X-API-Key": "test-key"}


def test_office_task_route_only_returns_pmo_route(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/office/tasks",
        headers=auth_headers(monkeypatch),
        json={
            "task": "Напиши короткий пост о запуске ИИ-офиса",
            "route_only": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "routed"
    assert body["requested_agent"] == "pmo"
    assert body["handled_by"] == "copywriter"
    assert body["task_id"].startswith("api_")


def test_office_task_executes_with_fake_provider_without_openai_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER_PRIMARY", "fake")
    monkeypatch.setenv("MODEL_PROVIDER_FALLBACK", "fake")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    office_api._agents.clear()
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/office/tasks",
        headers=auth_headers(monkeypatch),
        json={
            "task": "Сделай короткий отчет по KPI пилота",
            "route_only": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["handled_by"] == "data_analyst"
    assert "[fake:fake-local:data_analyst]" in body["result"]


def test_office_routes_endpoint_returns_subtasks(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/office/routes",
        headers=auth_headers(monkeypatch),
        json={"task": "Проверь инвойс и НДС"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["handled_by"] == "accountant"
    assert body["subtasks"]


def test_pmo_routes_payment_market_news_to_strategist():
    route = _route_task_by_rules(
        "актуальные новости рынка платежей Казахстана за последнюю неделю"
    )

    assert route == AgentRole.STRATEGIST


def test_pmo_does_not_match_accounting_act_inside_aktualnye():
    route = _route_task_by_rules("актуальные новости финтех рынка")

    assert route == AgentRole.STRATEGIST
