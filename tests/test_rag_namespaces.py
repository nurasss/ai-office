from rag.namespaces import get_agent_profile


def test_support_and_developer_have_isolated_namespaces():
    support = get_agent_profile("support")
    developer = get_agent_profile("developer")

    assert support["namespace"] == "agent_support"
    assert developer["namespace"] == "agent_developer"
    assert "agent_developer" not in support["allowed_namespaces"]
