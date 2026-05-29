from __future__ import annotations

from services.quality_gate_service import get_quality_gate_for_profile


def test_mcp_builder_quality_gate_uses_code_reviewer():
    quality_gate = get_quality_gate_for_profile("developer.mcp_builder")

    assert quality_gate == {
        "reviewer_profile": "developer.code_reviewer",
        "min_score": 85,
    }


def test_unknown_profile_has_no_quality_gate():
    assert get_quality_gate_for_profile("developer.unknown") is None
