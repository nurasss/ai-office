from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.office import router


def test_office_task_route_only_returns_pmo_route():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/office/tasks",
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


def test_office_routes_endpoint_returns_subtasks():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/office/routes",
        json={"task": "Проверь инвойс и НДС"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["handled_by"] == "accountant"
    assert body["subtasks"]
