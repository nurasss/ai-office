"""pgvector embeddings for knowledge chunks

Revision ID: 0004_pgvector_embeddings
Revises: 0003_p2_demo_product_schema
Create Date: 2026-06-02 03:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_pgvector_embeddings"
down_revision = "0003_p2_demo_product_schema"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if not _column_exists("knowledge_chunks", "embedding_model"):
        op.add_column("knowledge_chunks", sa.Column("embedding_model", sa.String(length=128), nullable=False, server_default=""))
    if not _column_exists("knowledge_chunks", "embedding_dimensions"):
        op.add_column("knowledge_chunks", sa.Column("embedding_dimensions", sa.Integer(), nullable=False, server_default="0"))
    if not _index_exists("knowledge_chunks", op.f("ix_knowledge_chunks_embedding_model")):
        op.create_index(
            op.f("ix_knowledge_chunks_embedding_model"),
            "knowledge_chunks",
            ["embedding_model"],
            unique=False,
        )

    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector(1536)")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw "
            "ON knowledge_chunks USING hnsw (embedding_vector vector_cosine_ops)"
        )
    else:
        if not _column_exists("knowledge_chunks", "embedding_vector"):
            op.add_column("knowledge_chunks", sa.Column("embedding_vector", sa.Text(), nullable=True))

    if dialect == "postgresql":
        op.alter_column("knowledge_chunks", "embedding_model", server_default=None)
        op.alter_column("knowledge_chunks", "embedding_dimensions", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
        op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding_vector")
    else:
        op.drop_column("knowledge_chunks", "embedding_vector")

    op.drop_index(op.f("ix_knowledge_chunks_embedding_model"), table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "embedding_dimensions")
    op.drop_column("knowledge_chunks", "embedding_model")
