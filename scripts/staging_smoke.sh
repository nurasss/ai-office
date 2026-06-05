#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${AI_OFFICE_API_KEY:-}"
ADMIN_TOKEN="${AI_OFFICE_ADMIN_TOKEN:-}"

curl_json() {
  curl -fsS "$@"
}

echo "Checking health at $BASE_URL"
curl_json "$BASE_URL/health" >/dev/null
curl_json "$BASE_URL/ready" >/dev/null

echo "Checking protected API behavior"
unauth_status="$(curl -sS -o /dev/null -w "%{http_code}" "$BASE_URL/api/conversations" || true)"
if [[ "$unauth_status" == "200" ]]; then
  echo "Expected /api/conversations to require auth, got 200"
  exit 1
fi

if [[ -n "$API_KEY" ]]; then
  curl_json -H "X-API-Key: $API_KEY" "$BASE_URL/api/conversations" >/dev/null
  curl_json \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"task":"Smoke route only check","route_only":true}' \
    "$BASE_URL/api/office/tasks" >/dev/null
else
  echo "AI_OFFICE_API_KEY not set; skipping authenticated public API smoke."
fi

if [[ -n "$ADMIN_TOKEN" ]]; then
  curl_json -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE_URL/dashboard" >/dev/null
  curl_json -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE_URL/api/metrics/summary" >/dev/null
else
  echo "AI_OFFICE_ADMIN_TOKEN not set; skipping admin smoke."
fi

echo "Staging smoke passed."
