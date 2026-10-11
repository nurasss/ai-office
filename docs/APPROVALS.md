# Approvals

Dangerous tools create a pending `approval` and set the task to `waiting_approval`.

API:

- `GET /api/approvals`
- `GET /api/approvals/{id}`
- `POST /api/approvals/{id}/approve`
- `POST /api/approvals/{id}/reject`

Approval decisions are written to `audit_events`. The MVP resumes by re-queueing the task or retrying from the API/worker path.

In P1, an approved tool call executes the stored `tool_calls.arguments_json` through the registered adapter. Success marks the tool call and task completed; failure marks the tool call failed and records `tool.failed`.
