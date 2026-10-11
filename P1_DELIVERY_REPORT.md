# P1 Delivery Report

## Что было сделано

- Added Redis/RQ queue backend with DB-backed fallback:
  - `workers/rq_queue.py`
  - `workers/rq_worker.py`
  - `WORKER_BACKEND`
  - `RQ_QUEUE_NAME`
- Updated task creation to enqueue via Redis when available and fall back safely when unavailable.
- Added approved GitHub write execution:
  - `tools/github_client.py`
  - real `github.issue.create` execution after approval when `ENABLE_REAL_TOOLS=true`.
- Added DB-backed knowledge ingestion and retrieval:
  - `rag/ingestion.py`
  - `rag/pgvector_store.py`
  - `rag/retrieval.py`
  - `/api/knowledge/upload`
  - `/api/knowledge/documents`
  - `/api/knowledge/search`
- Added minimal admin pages:
  - `/admin/tasks`
  - `/admin/tasks/{id}`
  - `/admin/approvals`
  - `/admin/audit`
  - `/admin/costs`
  - `/admin/knowledge`
- Added baseline eval framework:
  - `evals/runner.py`
  - `evals/grading.py`
  - 5 baseline YAML cases.
- Added local smoke script: `scripts/pilot_smoke_test.sh`.
- Updated README and P1 docs for controlled pilot operation.

## Какие файлы изменены

- Updated core/config/API/docs/tests from P0.
- Added `workers/rq_queue.py`, `workers/rq_worker.py`.
- Added `tools/github_client.py`.
- Added `rag/ingestion.py`, `rag/pgvector_store.py`, `rag/retrieval.py`.
- Added `evals/` runner and cases.
- Added admin page handlers in `web/app.py`.
- Added P1 tests for RQ fallback, GitHub approval execution, DB RAG, admin pages and evals.

## Как запустить

```bash
cp .env.example .env
docker compose up -d postgres redis
alembic upgrade head
python run.py
```

Redis/RQ worker:

```bash
python -m workers.rq_worker
```

DB polling fallback worker:

```bash
python -m workers.runner
```

## Как протестировать

```bash
uv run pytest -q
uv run python -m evals.runner
env DATABASE_URL=sqlite:////private/tmp/ai_office_alembic_p1_check.db uv run alembic upgrade head
```

Smoke test with a running app:

```bash
bash scripts/pilot_smoke_test.sh
```

## Какие тесты прошли

- `uv run pytest -q`: `122 passed, 4 warnings`
- `uv run python -m evals.runner`: `total=5 passed=5 failed=0 pass_rate=1.0`
- Alembic on clean temp SQLite DB: passed.

## Какие ограничения остались

- RAG uses DB-backed chunks and deterministic fake embeddings; native pgvector similarity/indexing is still the next step.
- GitHub write execution supports approved issue creation; PR review comments and issue comments have client foundations but no separate ToolAdapter yet.
- Admin pages are intentionally minimal HTML, not a full dashboard frontend.
- Local smoke script assumes the app is already running.
- Default local `data/ai_office.db` may need Alembic stamp/migration cleanup if it was created before migrations.

## Что делать в P2

- Implement real pgvector column/index and cosine/inner-product search in Postgres.
- Add ToolAdapters for GitHub issue comments and PR comments.
- Add dashboard templates with filters and pagination.
- Add eval trend persistence and CI eval report artifacts.
- Add full local controlled-pilot boot script that starts/stops app and worker processes.
