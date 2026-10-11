from core.config import get_settings
from core.db import get_session, init_db, reset_db_engine
from services.audit_service import audit_log, list_audit_events


def test_audit_redacts_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'audit.db'}")
    get_settings.cache_clear()
    reset_db_engine()
    init_db()

    with get_session() as db:
        audit_log(
            db,
            workspace_id="default",
            action="security.pii_redacted",
            object_type="task",
            object_id="1",
            metadata={"raw": "token xoxb-1234567890-fake and email test@example.com"},
            commit=True,
        )
        events = list_audit_events(db)

        raw = events[0].metadata_json["raw"]
        assert "xoxb-" not in raw
        assert "test@example.com" not in raw
