"""Simple deterministic graders for pilot evals."""

from __future__ import annotations

from typing import Any


def grade_case(case: dict[str, Any], output: str, *, requires_approval: bool = False) -> dict[str, Any]:
    lowered = output.lower()
    missing = [item for item in case.get("expected_contains", []) if str(item).lower() not in lowered]
    forbidden = [item for item in case.get("forbidden_contains", []) if str(item).lower() in lowered]
    expected_approval = (case.get("tool_expectation") or {}).get("requires_approval")
    approval_ok = expected_approval is None or bool(expected_approval) == requires_approval
    passed = not missing and not forbidden and approval_ok
    return {
        "id": case.get("id"),
        "passed": passed,
        "missing": missing,
        "forbidden": forbidden,
        "approval_ok": approval_ok,
    }
