"""Add P0 production pilot schema.

Revision ID: 0002_p0_production_schema
Revises: 0001_initial_autonomous_core
Create Date: 2026-06-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_p0_production_schema"
down_revision = "0001_initial_autonomous_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workspaces_organization_id"), "workspaces", ["organization_id"], unique=False)
    op.create_index(op.f("ix_workspaces_status"), "workspaces", ["status"], unique=False)

    op.add_column("tasks", sa.Column("workspace_id", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("input_text", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("risk_level", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_tasks_workspace_id"), "tasks", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_tasks_risk_level"), "tasks", ["risk_level"], unique=False)

    op.create_table(
        "task_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_cost_usd", sa.Float(), nullable=False),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_runs_status"), "task_runs", ["status"], unique=False)
    op.create_index(op.f("ix_task_runs_task_id"), "task_runs", ["task_id"], unique=False)
    op.create_index(op.f("ix_task_runs_trace_id"), "task_runs", ["trace_id"], unique=False)

    for column in [
        sa.Column("task_run_id", sa.Integer(), nullable=True),
        sa.Column("agent_name", sa.String(length=64), nullable=True),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("input_text_hash", sa.String(length=128), nullable=True),
        sa.Column("output_text_hash", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    ]:
        op.add_column("agent_runs", column)
    op.create_index(op.f("ix_agent_runs_task_run_id"), "agent_runs", ["task_run_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_agent_name"), "agent_runs", ["agent_name"], unique=False)

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("task_run_id", sa.Integer(), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=64), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_run_id"], ["task_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tool_calls_agent_run_id"), "tool_calls", ["agent_run_id"], unique=False)
    op.create_index(op.f("ix_tool_calls_approval_id"), "tool_calls", ["approval_id"], unique=False)
    op.create_index(op.f("ix_tool_calls_idempotency_key"), "tool_calls", ["idempotency_key"], unique=False)
    op.create_index(op.f("ix_tool_calls_requires_approval"), "tool_calls", ["requires_approval"], unique=False)
    op.create_index(op.f("ix_tool_calls_risk_level"), "tool_calls", ["risk_level"], unique=False)
    op.create_index(op.f("ix_tool_calls_status"), "tool_calls", ["status"], unique=False)
    op.create_index(op.f("ix_tool_calls_task_id"), "tool_calls", ["task_id"], unique=False)
    op.create_index(op.f("ix_tool_calls_task_run_id"), "tool_calls", ["task_run_id"], unique=False)
    op.create_index(op.f("ix_tool_calls_tool_name"), "tool_calls", ["tool_name"], unique=False)

    for column in [
        sa.Column("tool_call_id", sa.Integer(), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=True),
        sa.Column("risk_level", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("arguments_json", sa.JSON(), nullable=True),
        sa.Column("dry_run_result", sa.JSON(), nullable=True),
    ]:
        op.add_column("approvals", column)
    op.create_index(op.f("ix_approvals_tool_call_id"), "approvals", ["tool_call_id"], unique=False)
    op.create_index(op.f("ix_approvals_tool_name"), "approvals", ["tool_name"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=128), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"], unique=False)
    op.create_index(op.f("ix_audit_events_actor_type"), "audit_events", ["actor_type"], unique=False)
    op.create_index(op.f("ix_audit_events_object_type"), "audit_events", ["object_type"], unique=False)
    op.create_index(op.f("ix_audit_events_task_id"), "audit_events", ["task_id"], unique=False)
    op.create_index(op.f("ix_audit_events_workspace_id"), "audit_events", ["workspace_id"], unique=False)

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("agent_namespace", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("sensitivity", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_documents_agent_namespace"), "knowledge_documents", ["agent_namespace"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_content_hash"), "knowledge_documents", ["content_hash"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_workspace_id"), "knowledge_documents", ["workspace_id"], unique=False)

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("agent_namespace", sa.String(length=128), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_chunks_agent_namespace"), "knowledge_chunks", ["agent_namespace"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_content_hash"), "knowledge_chunks", ["content_hash"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_document_id"), "knowledge_chunks", ["document_id"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_workspace_id"), "knowledge_chunks", ["workspace_id"], unique=False)

    op.create_table(
        "model_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("task_run_id", sa.Integer(), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_run_id"], ["task_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_usage_agent_run_id"), "model_usage", ["agent_run_id"], unique=False)
    op.create_index(op.f("ix_model_usage_model"), "model_usage", ["model"], unique=False)
    op.create_index(op.f("ix_model_usage_provider"), "model_usage", ["provider"], unique=False)
    op.create_index(op.f("ix_model_usage_task_run_id"), "model_usage", ["task_run_id"], unique=False)
    op.create_index(op.f("ix_model_usage_workspace_id"), "model_usage", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_model_usage_workspace_id"), table_name="model_usage")
    op.drop_index(op.f("ix_model_usage_task_run_id"), table_name="model_usage")
    op.drop_index(op.f("ix_model_usage_provider"), table_name="model_usage")
    op.drop_index(op.f("ix_model_usage_model"), table_name="model_usage")
    op.drop_index(op.f("ix_model_usage_agent_run_id"), table_name="model_usage")
    op.drop_table("model_usage")
    op.drop_index(op.f("ix_knowledge_chunks_workspace_id"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_document_id"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_content_hash"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_agent_namespace"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_documents_workspace_id"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_content_hash"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_agent_namespace"), table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index(op.f("ix_audit_events_workspace_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_task_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_object_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_action"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(op.f("ix_approvals_tool_name"), table_name="approvals")
    op.drop_index(op.f("ix_approvals_tool_call_id"), table_name="approvals")
    for column_name in [
        "dry_run_result",
        "arguments_json",
        "reason",
        "risk_level",
        "tool_name",
        "tool_call_id",
    ]:
        op.drop_column("approvals", column_name)
    op.drop_index(op.f("ix_tool_calls_tool_name"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_task_run_id"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_task_id"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_status"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_risk_level"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_requires_approval"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_idempotency_key"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_approval_id"), table_name="tool_calls")
    op.drop_index(op.f("ix_tool_calls_agent_run_id"), table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_index(op.f("ix_agent_runs_agent_name"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_task_run_id"), table_name="agent_runs")
    for column_name in [
        "latency_ms",
        "cost_usd",
        "output_tokens",
        "input_tokens",
        "output_text_hash",
        "input_text_hash",
        "model_name",
        "model_provider",
        "agent_name",
        "task_run_id",
    ]:
        op.drop_column("agent_runs", column_name)
    op.drop_index(op.f("ix_task_runs_trace_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_task_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_status"), table_name="task_runs")
    op.drop_table("task_runs")
    op.drop_index(op.f("ix_tasks_risk_level"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_workspace_id"), table_name="tasks")
    op.drop_column("tasks", "risk_level")
    op.drop_column("tasks", "input_text")
    op.drop_column("tasks", "workspace_id")
    op.drop_index(op.f("ix_workspaces_status"), table_name="workspaces")
    op.drop_index(op.f("ix_workspaces_organization_id"), table_name="workspaces")
    op.drop_table("workspaces")
