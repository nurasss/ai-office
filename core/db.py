"""SQLAlchemy database setup for the autonomous runtime."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import urlparse
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.config import Environment, get_settings
from core.models import Base

_engine: Engine | None = None
_engine_url: str | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _normalize_database_url(url: str) -> str:
    """Normalize common DATABASE_URL variants for SQLAlchemy."""
    value = (url or "").strip() or "sqlite:///data/ai_office.db"
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg2://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg2://", 1)
    return value


def _ensure_sqlite_parent(url: str) -> None:
    if not url.startswith("sqlite:///") or url == "sqlite:///:memory:":
        return
    raw_path = url.removeprefix("sqlite:///")
    if raw_path and raw_path != ":memory:":
        Path(raw_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def get_database_url() -> str:
    """Return the configured database URL with local SQLite fallback."""
    configured_url = get_settings().database_url
    if (
        os.getenv("VERCEL")
        and not os.getenv("DATABASE_URL")
        and configured_url == "sqlite:///data/ai_office.db"
    ):
        return "sqlite:////tmp/ai_office.db"
    return _normalize_database_url(configured_url)


def get_engine() -> Engine:
    """Create or reuse the SQLAlchemy engine for the current DATABASE_URL."""
    global _engine, _engine_url, _SessionLocal
    url = get_database_url()
    if _engine is not None and _engine_url == url:
        return _engine

    _ensure_sqlite_parent(url)
    engine_kwargs: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
    }
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            engine_kwargs["poolclass"] = StaticPool

    _engine = create_engine(url, **engine_kwargs)
    _engine_url = url
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def init_db(engine: Engine | None = None) -> None:
    """Create database tables for the MVP runtime."""
    Base.metadata.create_all(bind=engine or get_engine())


def should_auto_create_tables() -> bool:
    """Return whether runtime code may create tables automatically."""
    return get_settings().environment != Environment.PRODUCTION


def reset_db_engine() -> None:
    """Dispose cached engine, mainly for tests that swap DATABASE_URL."""
    global _engine, _engine_url, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_url = None
    _SessionLocal = None


def get_session() -> Session:
    """Return a new SQLAlchemy session."""
    get_engine()
    if _SessionLocal is None:
        raise RuntimeError("Database session factory was not initialized.")
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session."""
    if should_auto_create_tables():
        init_db()
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def database_connected() -> bool:
    """Return whether the configured database accepts a simple query."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def redis_connected() -> bool:
    """Return whether the configured Redis TCP endpoint is reachable."""
    redis_url = getattr(get_settings(), "redis_url", "")
    if not redis_url:
        return False
    try:
        parsed = urlparse(redis_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except Exception:
        return False
