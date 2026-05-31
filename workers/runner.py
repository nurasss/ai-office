"""CLI runner for local DB-backed worker execution."""

from __future__ import annotations

import time

from sqlalchemy import select

from core.db import get_session, init_db
from core.models import Task
from workers.tasks import execute_task


def run_once() -> list[int]:
    init_db()
    processed: list[int] = []
    with get_session() as db:
        task_ids = list(
            db.scalars(
                select(Task.id)
                .where(Task.status.in_(["pending", "queued"]))
                .order_by(Task.created_at.asc())
                .limit(10)
            )
        )
        for task_id in task_ids:
            execute_task(db, task_id)
            processed.append(task_id)
    return processed


def main() -> None:
    print("AI Office worker started. Press Ctrl+C to stop.")
    while True:
        processed = run_once()
        if processed:
            print(f"processed={processed}")
        time.sleep(2)


if __name__ == "__main__":
    main()
