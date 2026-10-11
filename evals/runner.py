"""Run baseline AI Office pilot evals in fake mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from evals.grading import grade_case

CASES_DIR = Path(__file__).resolve().parent / "cases"


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, list):
            cases.extend(data)
        else:
            cases.append(data)
    return cases


def fake_agent_output(case: dict[str, Any]) -> tuple[str, bool]:
    agent = case.get("agent", "pmo")
    expected = " ".join(str(item) for item in case.get("expected_contains", []))
    requires_approval = bool((case.get("tool_expectation") or {}).get("requires_approval", False))
    approval_text = "approval required" if requires_approval else "safe draft"
    return f"{agent} result: {expected}. mode: {approval_text}.", requires_approval


def run_evals() -> dict[str, Any]:
    cases = load_cases()
    results = []
    for case in cases:
        output, requires_approval = fake_agent_output(case)
        results.append(grade_case(case, output, requires_approval=requires_approval))
    failed = [result["id"] for result in results if not result["passed"]]
    total = len(results)
    passed = total - len(failed)
    return {
        "total": total,
        "passed": passed,
        "failed": len(failed),
        "pass_rate": round(passed / total, 4) if total else 0,
        "failed_ids": failed,
    }


def main() -> None:
    report = run_evals()
    print(
        f"total={report['total']} passed={report['passed']} failed={report['failed']} "
        f"pass_rate={report['pass_rate']}"
    )
    if report["failed_ids"]:
        print("failed_ids=" + ",".join(report["failed_ids"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
