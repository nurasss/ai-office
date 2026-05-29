"""Typed agent profile definitions for curated agency profile imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_BASE_AGENTS = {
    "pmo",
    "developer",
    "copywriter",
    "support",
    "analyst",
    "data_analyst",
    "strategist",
    "accountant",
}


DANGEROUS_TOOL_MARKERS = {
    "deploy",
    "production",
    "git.push",
    "git.merge",
    "filesystem.delete",
    "secrets.write",
    "crm.write",
    "email.send",
    "payments.charge",
    "shell.any",
}


@dataclass(frozen=True)
class AgentProfile:
    """Professional sub-role profile attached to an existing AI Office agent."""

    id: str
    name: str
    base_agent: str
    source: str
    source_path: str | None
    description: str
    system_prompt: str
    model_tier: str = "working"
    allowed_tools: list[str] = field(default_factory=list)
    rag_namespace: str | None = None
    output_contract: str | None = None
    quality_gate: dict[str, Any] | None = None

    def validate(self) -> None:
        """Validate profile metadata without granting any permissions."""
        if not self.id.strip():
            raise ValueError("AgentProfile.id is required")
        if not self.name.strip():
            raise ValueError("AgentProfile.name is required")
        if self.base_agent not in VALID_BASE_AGENTS:
            raise ValueError(f"Invalid base_agent: {self.base_agent}")
        if not self.system_prompt.strip():
            raise ValueError(f"Profile {self.id} has empty system_prompt")
        dangerous_tools = [
            tool
            for tool in self.allowed_tools
            if any(marker in tool.lower() for marker in DANGEROUS_TOOL_MARKERS)
        ]
        if dangerous_tools:
            raise ValueError(
                f"Profile {self.id} declares dangerous tools: {', '.join(dangerous_tools)}"
            )
