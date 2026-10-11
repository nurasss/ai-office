from tools.base import ToolRisk
from tools.policy import tool_requires_approval


def test_tool_policy_requires_approval_for_dangerous_risks():
    assert tool_requires_approval(ToolRisk.SAFE_READ) is False
    assert tool_requires_approval(ToolRisk.SAFE_DRAFT) is False
    assert tool_requires_approval(ToolRisk.HIGH_RISK_WRITE) is True
    assert tool_requires_approval(ToolRisk.EXTERNAL_SEND) is True
    assert tool_requires_approval(ToolRisk.DELETE_OR_DESTRUCTIVE) is True
