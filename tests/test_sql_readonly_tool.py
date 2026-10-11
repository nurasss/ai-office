from sqlalchemy import text

from core.config import get_settings
from core.db import get_engine, init_db, reset_db_engine
from tools.base import ToolContext
from tools.sql_tools import SQLReadOnlyTool, validate_readonly_sql


def test_sql_readonly_rejects_delete_and_multiple_statements():
    assert validate_readonly_sql("DELETE FROM users")[0] is False
    assert validate_readonly_sql("SELECT 1; SELECT 2")[0] is False
    assert validate_readonly_sql("SELECT 1")[0] is True


def test_sql_readonly_select_executes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'sql.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()
    with get_engine().begin() as connection:
        connection.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)"))
        connection.execute(text("INSERT INTO sample (name) VALUES ('ok')"))

    result = SQLReadOnlyTool().execute({"query": "SELECT id, name FROM sample", "limit": 10}, ToolContext())

    assert result.ok is True
    assert result.data["rows"] == [{"id": 1, "name": "ok"}]
