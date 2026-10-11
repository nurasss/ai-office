#!/usr/bin/env python3
"""Live pgvector smoke for Postgres deployments."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import get_settings  # noqa: E402
from core.db import get_engine  # noqa: E402


def main() -> int:
    settings = get_settings()
    engine = get_engine()
    with engine.connect() as connection:
        if connection.dialect.name != "postgresql":
            print("Not a Postgres database; pgvector smoke skipped.")
            return 0

        extension = connection.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar()
        if not extension:
            print("pgvector extension is missing.")
            return 1
        print(f"pgvector_extension={extension}")

        dimension = connection.execute(
            text(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'knowledge_chunks'::regclass AND attname = 'embedding_vector'"
            )
        ).scalar()
        if dimension is None:
            print("knowledge_chunks.embedding_vector column is missing.")
            return 1
        print(f"embedding_dimensions_expected={settings.embedding_dimensions}")

        index = connection.execute(
            text("SELECT indexname FROM pg_indexes WHERE indexname = 'ix_knowledge_chunks_embedding_hnsw'")
        ).scalar()
        if not index:
            print("HNSW index ix_knowledge_chunks_embedding_hnsw is missing.")
            return 1
        print("hnsw_index=ok")

        namespaces = connection.execute(
            text("SELECT DISTINCT agent_namespace FROM knowledge_documents ORDER BY agent_namespace LIMIT 20")
        ).scalars().all()
        print("namespaces=" + ",".join(namespaces))

    print("pgvector smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
