"""Worker task execution."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.orm import Session

from core.models import AgentRun, ModelUsage, Task, TaskRun, utc_now
from models.router import ModelRequest, PilotModelRouter, estimate_cost
from security.pii import redact_pii
from security.prompt_injection import detect_prompt_injection
from services.audit_service import audit_log
from tools.base import ToolContext
from tools.registry import ToolExecutionService


def execute_task(db: Session, task_id: int) -> dict[str, object] | None:
    """Execute one task in deterministic safe pilot mode."""
    task = db.get(Task, task_id)
    if not task:
        return None

    task.status = "running"
    task.started_at = task.started_at or utc_now()
    task_run = TaskRun(task_id=task.id, status="running", trace_id=uuid.uuid4().hex)
    db.add(task_run)
    db.flush()
    audit_log(
        db,
        workspace_id=task.workspace_id or "default",
        task_id=task.id,
        actor_type="system",
        actor_id="worker",
        action="task.started",
        object_type="task_run",
        object_id=task_run.id,
        metadata={"trace_id": task_run.trace_id},
    )

    input_text = task.input_text or task.description or task.title
    injection_findings = detect_prompt_injection(input_text)
    if injection_findings:
        audit_log(
            db,
            workspace_id=task.workspace_id or "default",
            task_id=task.id,
            actor_type="system",
            actor_id="prompt_injection_guard",
            action="security.prompt_injection_detected",
            object_type="task",
            object_id=task.id,
            metadata={"findings": [finding.__dict__ for finding in injection_findings]},
        )

    redaction = redact_pii(input_text)
    if redaction.findings:
        audit_log(
            db,
            workspace_id=task.workspace_id or "default",
            task_id=task.id,
            actor_type="system",
            actor_id="pii_redactor",
            action="security.pii_redacted",
            object_type="task",
            object_id=task.id,
            metadata={"finding_kinds": sorted({finding.kind for finding in redaction.findings})},
        )

    agent_run = AgentRun(
        task_id=task.id,
        task_run_id=task_run.id,
        agent_id=task.assigned_agent,
        agent_name=task.assigned_agent,
        status="running",
        input={"text": redaction.redacted_text},
        input_text_hash=_hash_text(redaction.redacted_text),
        started_at=utc_now(),
    )
    db.add(agent_run)
    db.flush()
    audit_log(
        db,
        workspace_id=task.workspace_id or "default",
        task_id=task.id,
        actor_type="agent",
        actor_id=task.assigned_agent,
        action="agent.started",
        object_type="agent_run",
        object_id=agent_run.id,
        metadata={},
    )

    if _looks_like_github_issue_write(input_text):
        result = ToolExecutionService(db).call_tool(
            "github.issue.create",
            {
                "title": _derive_issue_title(task.title, input_text),
                "body": input_text,
            },
            ToolContext(
                workspace_id=task.workspace_id or "default",
                task_id=task.id,
                task_run_id=task_run.id,
                agent_run_id=agent_run.id,
                agent_name=task.assigned_agent,
            ),
        )
        agent_run.status = "waiting_approval"
        agent_run.output = {"tool_result": result.model_dump()}
        agent_run.completed_at = utc_now()
        task_run.status = "waiting_approval"
        task_run.finished_at = utc_now()
        task.status = "waiting_approval"
        db.commit()
        return {"status": "waiting_approval", "task_id": task.id, "approval_id": result.approval_id}

    router = PilotModelRouter()
    choice, response, model_input = router.generate(
        ModelRequest(
            task_type=task.assigned_agent,
            risk_level=task.risk_level or "safe",
            agent_name=task.assigned_agent,
            input_text=input_text,
            requires_reasoning=task.assigned_agent in {"pmo", "data_analyst"},
            requires_coding=task.assigned_agent == "developer",
            requires_finance=task.assigned_agent == "accountant",
        )
    )
    cost = estimate_cost(choice.provider, choice.model, response.input_tokens, response.output_tokens)
    agent_run.status = "completed"
    agent_run.model_provider = choice.provider
    agent_run.model_name = choice.model
    agent_run.output = {"text": response.text, "model_reason": choice.reason}
    agent_run.output_text_hash = _hash_text(response.text)
    agent_run.input_tokens = response.input_tokens
    agent_run.output_tokens = response.output_tokens
    agent_run.cost_usd = cost
    agent_run.latency_ms = response.latency_ms
    agent_run.completed_at = utc_now()
    usage = ModelUsage(
        workspace_id=task.workspace_id or "default",
        task_run_id=task_run.id,
        agent_run_id=agent_run.id,
        provider=choice.provider,
        model=choice.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=cost,
        latency_ms=response.latency_ms,
    )
    db.add(usage)
    task_run.status = "completed"
    task_run.finished_at = utc_now()
    task_run.total_cost_usd = cost
    task_run.total_input_tokens = response.input_tokens
    task_run.total_output_tokens = response.output_tokens
    task.status = "completed"
    task.completed_at = task_run.finished_at
    task.result_summary = response.text[:800]
    task.result_payload = {
        "answer": response.text,
        "model": choice.model,
        "provider": choice.provider,
        "redacted_model_input_hash": _hash_text(model_input),
    }
    audit_log(
        db,
        workspace_id=task.workspace_id or "default",
        task_id=task.id,
        actor_type="model",
        actor_id=choice.provider,
        action="model.called",
        object_type="agent_run",
        object_id=agent_run.id,
        metadata={"model": choice.model, "tier": choice.tier, "cost_usd": cost, "reason": choice.reason},
    )
    audit_log(
        db,
        workspace_id=task.workspace_id or "default",
        task_id=task.id,
        actor_type="agent",
        actor_id=task.assigned_agent,
        action="agent.completed",
        object_type="agent_run",
        object_id=agent_run.id,
        metadata={"status": "completed"},
    )
    audit_log(
        db,
        workspace_id=task.workspace_id or "default",
        task_id=task.id,
        actor_type="system",
        actor_id="worker",
        action="task.completed",
        object_type="task",
        object_id=task.id,
        metadata={"task_run_id": task_run.id},
    )
    db.commit()
    return {"status": "completed", "task_id": task.id, "task_run_id": task_run.id}


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _looks_like_github_issue_write(text: str) -> bool:
    lowered = text.lower()
    return ("github" in lowered or "гитхаб" in lowered) and (
        "create issue" in lowered
        or "создай issue" in lowered
        or "создать issue" in lowered
        or "создай github issue" in lowered
    )


def _derive_issue_title(title: str, text: str) -> str:
    candidate = title.strip() or text.strip().splitlines()[0]
    return candidate[:120] or "AI Office task"
