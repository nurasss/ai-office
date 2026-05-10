"""RAG namespace policy for the seven AI Office agents."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

COMMON_NAMESPACE = "common_corporate"
INCIDENT_NAMESPACE = "common_incidents"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_CATALOG_PATH = PROJECT_ROOT / "config" / "knowledge_sources.yaml"


@lru_cache(maxsize=1)
def load_knowledge_catalog() -> dict[str, Any]:
    """Load the agent knowledge catalog from config/knowledge_sources.yaml."""
    if not KNOWLEDGE_CATALOG_PATH.exists():
        return {}

    with open(KNOWLEDGE_CATALOG_PATH, "r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def get_agent_profile(agent_id: str) -> dict[str, Any]:
    """Return a normalized RAG profile for an agent."""
    catalog = load_knowledge_catalog()
    agent_config = catalog.get("agents", {}).get(agent_id, {})
    common = catalog.get("common", {})

    namespace = agent_config.get("namespace", f"agent_{agent_id}")
    include_common = agent_config.get("include_common", True)

    allowed_namespaces = [namespace]
    if include_common:
        allowed_namespaces.insert(0, common.get("namespace", COMMON_NAMESPACE))

    return {
        "agent_id": agent_id,
        "namespace": namespace,
        "allowed_namespaces": allowed_namespaces,
        "forbidden_namespaces": agent_config.get("forbidden_namespaces", []),
        "sources": agent_config.get("sources", []),
        "common_sources": common.get("sources", []),
        "include_common": include_common,
    }


def all_agent_namespaces() -> dict[str, str]:
    """Return {agent_id: namespace} for ingestion and diagnostics."""
    catalog = load_knowledge_catalog()
    agents = catalog.get("agents", {})
    return {
        agent_id: config.get("namespace", f"agent_{agent_id}")
        for agent_id, config in agents.items()
    }
