"""Curated agent profile registry for adapted agency-agents profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.agent_profiles import AgentProfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "agents" / "profile_manifest.json"


PROFILE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "developer.mcp_builder",
        ("mcp", "tool", "tools", "server", "context protocol"),
    ),
    (
        "developer.code_reviewer",
        ("review", "pr", "pull request", "code review"),
    ),
    (
        "developer.security_engineer",
        ("security", "secret", "auth", "token", "webhook", "whitelist"),
    ),
    (
        "developer.devops_automator",
        ("deploy", "docker", "ci", "cd", "server", "nginx", "systemd"),
    ),
    (
        "developer.backend_architect",
        ("backend", "api", "integration", "endpoint", "database"),
    ),
    (
        "pmo.project_manager",
        ("plan", "roadmap", "tasks", "project", "sprint"),
    ),
    (
        "copywriter.technical_writer",
        ("docs", "readme", "manual", "documentation"),
    ),
    (
        "support.customer_support",
        ("support", "ticket", "faq", "customer"),
    ),
    (
        "analyst.data_engineer",
        ("data", "csv", "analytics", "pipeline"),
    ),
    (
        "strategist.product_strategist",
        ("strategy", "market", "product", "roadmap"),
    ),
    (
        "accountant.document_reviewer",
        ("invoice", "document", "pdf", "act", "receipt"),
    ),
]


BASE_AGENT_ALIASES = {
    "analyst": "data_analyst",
}


class AgentProfileRegistry:
    """Load and query local curated profile metadata."""

    def __init__(self, manifest_path: str | Path | None = None) -> None:
        self.manifest_path = Path(manifest_path or DEFAULT_MANIFEST_PATH)
        if not self.manifest_path.is_absolute():
            self.manifest_path = PROJECT_ROOT / self.manifest_path
        self._profiles: dict[str, AgentProfile] | None = None

    def list_profiles(self) -> list[AgentProfile]:
        self._ensure_loaded()
        return list((self._profiles or {}).values())

    def get_profile(self, profile_id: str) -> AgentProfile | None:
        self._ensure_loaded()
        return (self._profiles or {}).get(profile_id)

    def find_profiles_for_base_agent(self, base_agent: str) -> list[AgentProfile]:
        self._ensure_loaded()
        normalized = BASE_AGENT_ALIASES.get(base_agent, base_agent)
        return [
            profile
            for profile in (self._profiles or {}).values()
            if BASE_AGENT_ALIASES.get(profile.base_agent, profile.base_agent) == normalized
        ]

    def select_profile_for_task(
        self,
        task_text: str,
        base_agent: str | None = None,
    ) -> AgentProfile | None:
        """Select a profile by deterministic keyword matching."""
        self._ensure_loaded()
        if not self._profiles:
            return None

        text = task_text.lower()
        normalized_base = BASE_AGENT_ALIASES.get(base_agent or "", base_agent or "")
        for profile_id, keywords in PROFILE_KEYWORDS:
            profile = self._profiles.get(profile_id)
            if not profile:
                continue
            if normalized_base:
                profile_base = BASE_AGENT_ALIASES.get(profile.base_agent, profile.base_agent)
                if profile_base != normalized_base:
                    continue
            if any(keyword in text for keyword in keywords):
                return profile
        return None

    def _ensure_loaded(self) -> None:
        if self._profiles is not None:
            return
        self._profiles = {}
        if not self.manifest_path.exists():
            return

        raw_profiles = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw_profiles, list):
            raise ValueError("Profile manifest must be a list.")

        seen_ids: set[str] = set()
        for raw_profile in raw_profiles:
            if not isinstance(raw_profile, dict):
                raise ValueError("Profile manifest entries must be objects.")
            profile = self._build_profile(raw_profile)
            if profile.id in seen_ids:
                raise ValueError(f"Duplicate profile id: {profile.id}")
            profile.validate()
            seen_ids.add(profile.id)
            self._profiles[profile.id] = profile

    def _build_profile(self, raw_profile: dict[str, Any]) -> AgentProfile:
        source_path = raw_profile.get("source_path")
        prompt = ""
        if source_path:
            path = Path(str(source_path))
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            if not path.exists():
                raise ValueError(f"Profile source_path does not exist: {source_path}")
            prompt = path.read_text(encoding="utf-8")

        return AgentProfile(
            id=str(raw_profile.get("id", "")),
            name=str(raw_profile.get("name", "")),
            base_agent=str(raw_profile.get("base_agent", "")),
            source=str(raw_profile.get("source", "")),
            source_path=str(source_path) if source_path else None,
            description=str(raw_profile.get("description", "")),
            system_prompt=prompt,
            model_tier=str(raw_profile.get("model_tier", "working")),
            allowed_tools=list(raw_profile.get("allowed_tools") or []),
            rag_namespace=raw_profile.get("rag_namespace"),
            output_contract=raw_profile.get("output_contract"),
            quality_gate=raw_profile.get("quality_gate"),
        )
