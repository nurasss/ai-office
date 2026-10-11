#!/usr/bin/env python3
"""Check database migration readiness and pgvector objects."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db import get_engine  # noqa: E402

REQUIRED_TABLES = {
    "tasks",
    "task_runs",
    "agent_runs",
    "approvals",
    "audit_events",
    "knowledge_documents",
    "knowledge_chunks",
    "model_usage",
    "scheduled_jobs",
    "scheduled_job_runs",
    "scheduler_locks",
}


def main() -> int:
    engine = get_engine()
    config = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    failures: list[str] = []

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current = context.get_current_revision()
        dialect = connection.dialect.name
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        print(f"database_dialect={dialect}")
        print(f"alembic_current={current or 'none'}")
        print(f"alembic_head={head}")
        if current != head:
            failures.append("Alembic current revision does not match head.")

        missing_tables = sorted(REQUIRED_TABLES - tables)
        if missing_tables:
            failures.append("Missing runtime tables: " + ", ".join(missing_tables))
        else:
            print("runtime_tables=ok")

        if dialect == "postgresql":
            vector_extension = connection.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
            if not vector_extension:
                failures.append("Postgres extension vector is not installed.")
            else:
                print("pgvector_extension=ok")

            hnsw_index = connection.execute(
                text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_knowledge_chunks_embedding_hnsw'")
            ).scalar()
            if not hnsw_index:
                failures.append("HNSW index ix_knowledge_chunks_embedding_hnsw is missing.")
            else:
                print("knowledge_chunks_hnsw_index=ok")
        else:
            print("pgvector_extension=skipped_for_non_postgres")
            print("knowledge_chunks_hnsw_index=skipped_for_non_postgres")

    if failures:
        print("Migration readiness failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Migration readiness passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
