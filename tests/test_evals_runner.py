from evals.grading import grade_case
from evals.runner import run_evals


def test_eval_runner_baseline_passes():
    report = run_evals()

    assert report["total"] >= 5
    assert report["failed"] == 0


def test_eval_grader_catches_forbidden_text():
    result = grade_case(
        {"id": "x", "expected_contains": ["ok"], "forbidden_contains": ["secret"]},
        "ok secret",
    )

    assert result["passed"] is False
    assert result["forbidden"] == ["secret"]
