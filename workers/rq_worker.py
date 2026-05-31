"""Run an RQ worker for AI Office tasks."""

from __future__ import annotations

from redis import Redis
from rq import Worker

from core.config import get_settings


def main() -> None:
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    worker = Worker([settings.rq_queue_name], connection=connection)
    worker.work()


if __name__ == "__main__":
    main()
