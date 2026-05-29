from __future__ import annotations

from pathlib import Path

from core.agent_profiles import VALID_BASE_AGENTS
from services.agent_profile_registry import AgentProfileRegistry


def test_registry_loads_all_curated_profiles():
    profiles = AgentProfileRegistry().list_profiles()

    assert len(profiles) == 11
    assert {profile.id for profile in profiles} >= {
        "developer.backend_architect",
        "developer.code_reviewer",
        "developer.mcp_builder",
        "developer.security_engineer",
        "developer.devops_automator",
        "pmo.project_manager",
        "copywriter.technical_writer",
        "support.customer_support",
        "analyst.data_engineer",
        "strategist.product_strategist",
        "accountant.document_reviewer",
    }


def test_profile_ids_are_unique_and_base_agents_are_valid():
    profiles = AgentProfileRegistry().list_profiles()
    profile_ids = [profile.id for profile in profiles]

    assert len(profile_ids) == len(set(profile_ids))
    assert all(profile.base_agent in VALID_BASE_AGENTS for profile in profiles)


def test_profile_markdown_files_exist_and_have_prompts():
    profiles = AgentProfileRegistry().list_profiles()

    for profile in profiles:
        assert profile.source_path
        assert Path(profile.source_path).exists()
        assert profile.system_prompt.strip()
        assert "Do not bypass AI Office approvals." in profile.system_prompt
