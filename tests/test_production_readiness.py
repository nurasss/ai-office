from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from core.auth import get_current_user, require_admin
from core.config import get_settings
from core.db import get_db, reset_db_engine
from core.models import Base
from core.production import validate_production_settings


def _clear_settings():
    get_settings.cache_clear()
    reset_db_engine()


def test_production_preflight_flags_insecure_config(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AI_OFFICE_REQUIRE_API_KEY", "false")
    monkeypatch.setenv("AI_OFFICE_API_KEY", "change-me")
    monkeypatch.setenv("AI_OFFICE_ADMIN_TOKEN", "change-me")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///data/ai_office.db")
    monkeypatch.setenv("MODEL_PROVIDER_PRIMARY", "fake")
    _clear_settings()

    errors = validate_production_settings(get_settings())

    assert "AI_OFFICE_REQUIRE_API_KEY must be true." in errors
    assert "DATABASE_URL must point to Postgres, not SQLite." in errors
    assert "MODEL_PROVIDER_PRIMARY cannot be fake." in errors


def test_production_rejects_header_spoofed_identity(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    _clear_settings()
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(user: dict[str, str] = Depends(get_current_user)):
        return user

    response = TestClient(app).get("/whoami", headers={"X-User-Role": "owner"})

    assert response.status_code == 401


def test_require_admin_uses_dedicated_token(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AI_OFFICE_ADMIN_TOKEN", "admin-secret-for-test")
    _clear_settings()
    app = FastAPI()

    @app.get("/admin", dependencies=[Depends(require_admin)])
    async def admin():
        return {"ok": True}

    client = TestClient(app)

    assert client.get("/admin").status_code == 401
    assert client.get("/admin", headers={"Authorization": "Bearer admin-secret-for-test"}).status_code == 200


def test_get_db_does_not_create_tables_in_production(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'prod.db'}")
    _clear_settings()
    called = False

    def fail_create_all(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("create_all must not run in production get_db")

    monkeypatch.setattr(Base.metadata, "create_all", fail_create_all)

    dependency = get_db()
    session = next(dependency)
    session.close()
    with pytest.raises(StopIteration):
        next(dependency)

    assert called is False
