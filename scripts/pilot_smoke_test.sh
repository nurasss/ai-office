#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "Checking /health"
curl -fsS "$BASE_URL/health" >/dev/null

echo "Checking /ready"
curl -fsS "$BASE_URL/ready" >/dev/null

echo "Creating safe task"
SAFE_TASK_ID=$(uv run python - <<'PY'
import json, os, urllib.request
base = os.environ.get("BASE_URL", "http://localhost:8000")
payload = json.dumps({"title": "Pilot smoke safe task", "input_text": "Сделай безопасный план пилота"}).encode()
req = urllib.request.Request(f"{base}/api/tasks", data=payload, headers={"Content-Type": "application/json"}, method="POST")
print(json.loads(urllib.request.urlopen(req).read())["id"])
PY
)
export SAFE_TASK_ID

echo "Running worker job for task $SAFE_TASK_ID"
uv run python - <<PY
from workers.rq_queue import process_task_job
print(process_task_job(int("$SAFE_TASK_ID")))
PY

echo "Checking safe task completed"
uv run python - <<'PY'
import json, os, urllib.request
base = os.environ.get("BASE_URL", "http://localhost:8000")
task_id = os.environ["SAFE_TASK_ID"]
task = json.loads(urllib.request.urlopen(f"{base}/api/tasks/{task_id}").read())
assert task["status"] == "completed", task
PY

echo "Creating GitHub write task"
GITHUB_TASK_ID=$(uv run python - <<'PY'
import json, os, urllib.request
base = os.environ.get("BASE_URL", "http://localhost:8000")
payload = json.dumps({"title": "GitHub smoke write", "input_text": "Создай GitHub issue для smoke test", "agent_hint": "developer"}).encode()
req = urllib.request.Request(f"{base}/api/tasks", data=payload, headers={"Content-Type": "application/json"}, method="POST")
print(json.loads(urllib.request.urlopen(req).read())["id"])
PY
)

uv run python - <<PY
from workers.rq_queue import process_task_job
print(process_task_job(int("$GITHUB_TASK_ID")))
PY

echo "Checking pending approval, audit and metrics"
curl -fsS "$BASE_URL/api/approvals?status=pending" >/dev/null
curl -fsS "$BASE_URL/api/audit" >/dev/null
curl -fsS "$BASE_URL/api/metrics/summary" >/dev/null

echo "Pilot smoke test passed"
