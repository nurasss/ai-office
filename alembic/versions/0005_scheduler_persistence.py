"""scheduler persistence, locks, and run history

Revision ID: 0005_scheduler_persistence
Revises: 0004_pgvector_embeddings
Create Date: 2026-06-02 04:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_scheduler_persistence"
down_revision = "0004_pgvector_embeddings"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("scheduled_jobs"):
        op.create_table(
            "scheduled_jobs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("job_key", sa.String(length=128), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("schedule_type", sa.String(length=64), nullable=False),
            sa.Column("cron_expr", sa.String(length=128), nullable=True),
            sa.Column("interval_seconds", sa.Integer(), nullable=True),
            sa.Column("timezone", sa.String(length=64), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("scheduled_jobs", op.f("ix_scheduled_jobs_enabled")):
        op.create_index(op.f("ix_scheduled_jobs_enabled"), "scheduled_jobs", ["enabled"], unique=False)
    if not _index_exists("scheduled_jobs", op.f("ix_scheduled_jobs_job_key")):
        op.create_index(op.f("ix_scheduled_jobs_job_key"), "scheduled_jobs", ["job_key"], unique=True)
    if not _index_exists("scheduled_jobs", op.f("ix_scheduled_jobs_next_run_at")):
        op.create_index(op.f("ix_scheduled_jobs_next_run_at"), "scheduled_jobs", ["next_run_at"], unique=False)
    if not _index_exists("scheduled_jobs", op.f("ix_scheduled_jobs_schedule_type")):
        op.create_index(op.f("ix_scheduled_jobs_schedule_type"), "scheduled_jobs", ["schedule_type"], unique=False)

    if not _table_exists("scheduled_job_runs"):
        op.create_table(
            "scheduled_job_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("job_id", sa.Integer(), nullable=True),
            sa.Column("job_key", sa.String(length=128), nullable=False),
            sa.Column("idempotency_key", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("result_json", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_task_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["created_task_id"], ["tasks.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["job_id"], ["scheduled_jobs.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("scheduled_job_runs", op.f("ix_scheduled_job_runs_created_task_id")):
        op.create_index(op.f("ix_scheduled_job_runs_created_task_id"), "scheduled_job_runs", ["created_task_id"], unique=False)
    if not _index_exists("scheduled_job_runs", op.f("ix_scheduled_job_runs_idempotency_key")):
        op.create_index(op.f("ix_scheduled_job_runs_idempotency_key"), "scheduled_job_runs", ["idempotency_key"], unique=True)
    if not _index_exists("scheduled_job_runs", op.f("ix_scheduled_job_runs_job_id")):
        op.create_index(op.f("ix_scheduled_job_runs_job_id"), "scheduled_job_runs", ["job_id"], unique=False)
    if not _index_exists("scheduled_job_runs", op.f("ix_scheduled_job_runs_job_key")):
        op.create_index(op.f("ix_scheduled_job_runs_job_key"), "scheduled_job_runs", ["job_key"], unique=False)
    if not _index_exists("scheduled_job_runs", op.f("ix_scheduled_job_runs_status")):
        op.create_index(op.f("ix_scheduled_job_runs_status"), "scheduled_job_runs", ["status"], unique=False)

    if not _table_exists("scheduler_locks"):
        op.create_table(
            "scheduler_locks",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("lock_key", sa.String(length=128), nullable=False),
            sa.Column("owner_id", sa.String(length=128), nullable=False),
            sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("scheduler_locks", op.f("ix_scheduler_locks_expires_at")):
        op.create_index(op.f("ix_scheduler_locks_expires_at"), "scheduler_locks", ["expires_at"], unique=False)
    if not _index_exists("scheduler_locks", op.f("ix_scheduler_locks_lock_key")):
        op.create_index(op.f("ix_scheduler_locks_lock_key"), "scheduler_locks", ["lock_key"], unique=True)
    if not _index_exists("scheduler_locks", op.f("ix_scheduler_locks_owner_id")):
        op.create_index(op.f("ix_scheduler_locks_owner_id"), "scheduler_locks", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scheduler_locks_owner_id"), table_name="scheduler_locks")
    op.drop_index(op.f("ix_scheduler_locks_lock_key"), table_name="scheduler_locks")
    op.drop_index(op.f("ix_scheduler_locks_expires_at"), table_name="scheduler_locks")
    op.drop_table("scheduler_locks")

    op.drop_index(op.f("ix_scheduled_job_runs_status"), table_name="scheduled_job_runs")
    op.drop_index(op.f("ix_scheduled_job_runs_job_key"), table_name="scheduled_job_runs")
    op.drop_index(op.f("ix_scheduled_job_runs_job_id"), table_name="scheduled_job_runs")
    op.drop_index(op.f("ix_scheduled_job_runs_idempotency_key"), table_name="scheduled_job_runs")
    op.drop_index(op.f("ix_scheduled_job_runs_created_task_id"), table_name="scheduled_job_runs")
    op.drop_table("scheduled_job_runs")

    op.drop_index(op.f("ix_scheduled_jobs_schedule_type"), table_name="scheduled_jobs")
    op.drop_index(op.f("ix_scheduled_jobs_next_run_at"), table_name="scheduled_jobs")
    op.drop_index(op.f("ix_scheduled_jobs_job_key"), table_name="scheduled_jobs")
    op.drop_index(op.f("ix_scheduled_jobs_enabled"), table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")
