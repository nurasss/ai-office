"""Add P2 demo product schema.

Revision ID: 0003_p2_demo_product_schema
Revises: 0002_p0_production_schema
Create Date: 2026-06-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_p2_demo_product_schema"
down_revision = "0002_p0_production_schema"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("user_profiles"):
        op.create_table(
            "user_profiles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("external_id", sa.String(length=128), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("primary_project_slug", sa.String(length=120), nullable=False),
            sa.Column("communication_style", sa.Text(), nullable=False),
            sa.Column("goals_summary", sa.Text(), nullable=False),
            sa.Column("preferences_json", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("external_id"),
        )
    if not _index_exists("user_profiles", op.f("ix_user_profiles_external_id")):
        op.create_index(op.f("ix_user_profiles_external_id"), "user_profiles", ["external_id"], unique=False)

    if not _table_exists("goals"):
        op.create_table(
            "goals",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("user_external_id", sa.String(length=128), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("autonomy_enabled", sa.Boolean(), nullable=False),
            sa.Column("plan_json", sa.JSON(), nullable=False),
            sa.Column("last_daily_plan", sa.Text(), nullable=False),
            sa.Column("last_review_summary", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("goals", op.f("ix_goals_status")):
        op.create_index(op.f("ix_goals_status"), "goals", ["status"], unique=False)
    if not _index_exists("goals", op.f("ix_goals_user_external_id")):
        op.create_index(op.f("ix_goals_user_external_id"), "goals", ["user_external_id"], unique=False)
    if not _index_exists("goals", op.f("ix_goals_workspace_id")):
        op.create_index(op.f("ix_goals_workspace_id"), "goals", ["workspace_id"], unique=False)

    if not _table_exists("generated_sites"):
        op.create_table(
            "generated_sites",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("site_id", sa.String(length=160), nullable=False),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("user_external_id", sa.String(length=128), nullable=False),
            sa.Column("project_slug", sa.String(length=120), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("site_type", sa.String(length=64), nullable=False),
            sa.Column("directory_path", sa.Text(), nullable=False),
            sa.Column("public_path", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("site_id"),
        )
    if not _index_exists("generated_sites", op.f("ix_generated_sites_project_slug")):
        op.create_index(op.f("ix_generated_sites_project_slug"), "generated_sites", ["project_slug"], unique=False)
    if not _index_exists("generated_sites", op.f("ix_generated_sites_site_id")):
        op.create_index(op.f("ix_generated_sites_site_id"), "generated_sites", ["site_id"], unique=False)
    if not _index_exists("generated_sites", op.f("ix_generated_sites_status")):
        op.create_index(op.f("ix_generated_sites_status"), "generated_sites", ["status"], unique=False)
    if not _index_exists("generated_sites", op.f("ix_generated_sites_user_external_id")):
        op.create_index(op.f("ix_generated_sites_user_external_id"), "generated_sites", ["user_external_id"], unique=False)
    if not _index_exists("generated_sites", op.f("ix_generated_sites_workspace_id")):
        op.create_index(op.f("ix_generated_sites_workspace_id"), "generated_sites", ["workspace_id"], unique=False)

    if not _table_exists("generated_tools"):
        op.create_table(
            "generated_tools",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tool_id", sa.String(length=160), nullable=False),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("user_external_id", sa.String(length=128), nullable=False),
            sa.Column("project_slug", sa.String(length=120), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("tool_type", sa.String(length=64), nullable=False),
            sa.Column("directory_path", sa.Text(), nullable=False),
            sa.Column("public_path", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tool_id"),
        )
    if not _index_exists("generated_tools", op.f("ix_generated_tools_project_slug")):
        op.create_index(op.f("ix_generated_tools_project_slug"), "generated_tools", ["project_slug"], unique=False)
    if not _index_exists("generated_tools", op.f("ix_generated_tools_status")):
        op.create_index(op.f("ix_generated_tools_status"), "generated_tools", ["status"], unique=False)
    if not _index_exists("generated_tools", op.f("ix_generated_tools_tool_id")):
        op.create_index(op.f("ix_generated_tools_tool_id"), "generated_tools", ["tool_id"], unique=False)
    if not _index_exists("generated_tools", op.f("ix_generated_tools_user_external_id")):
        op.create_index(op.f("ix_generated_tools_user_external_id"), "generated_tools", ["user_external_id"], unique=False)
    if not _index_exists("generated_tools", op.f("ix_generated_tools_workspace_id")):
        op.create_index(op.f("ix_generated_tools_workspace_id"), "generated_tools", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_generated_tools_workspace_id"), table_name="generated_tools")
    op.drop_index(op.f("ix_generated_tools_user_external_id"), table_name="generated_tools")
    op.drop_index(op.f("ix_generated_tools_tool_id"), table_name="generated_tools")
    op.drop_index(op.f("ix_generated_tools_status"), table_name="generated_tools")
    op.drop_index(op.f("ix_generated_tools_project_slug"), table_name="generated_tools")
    op.drop_table("generated_tools")
    op.drop_index(op.f("ix_generated_sites_workspace_id"), table_name="generated_sites")
    op.drop_index(op.f("ix_generated_sites_user_external_id"), table_name="generated_sites")
    op.drop_index(op.f("ix_generated_sites_status"), table_name="generated_sites")
    op.drop_index(op.f("ix_generated_sites_site_id"), table_name="generated_sites")
    op.drop_index(op.f("ix_generated_sites_project_slug"), table_name="generated_sites")
    op.drop_table("generated_sites")
    op.drop_index(op.f("ix_goals_workspace_id"), table_name="goals")
    op.drop_index(op.f("ix_goals_user_external_id"), table_name="goals")
    op.drop_index(op.f("ix_goals_status"), table_name="goals")
    op.drop_table("goals")
    op.drop_index(op.f("ix_user_profiles_external_id"), table_name="user_profiles")
    op.drop_table("user_profiles")
