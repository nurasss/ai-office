"""Quality gate lookup helpers for agent profiles."""

from __future__ import annotations

from services.agent_profile_registry import AgentProfileRegistry


def get_quality_gate_for_profile(
    profile_id: str,
    registry: AgentProfileRegistry | None = None,
) -> dict | None:
    """Return configured quality gate metadata for a profile, if any."""
    active_registry = registry or AgentProfileRegistry()
    profile = active_registry.get_profile(profile_id)
    if not profile:
        return None
    return profile.quality_gate
