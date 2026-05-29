from harness.runtime import BaseTool, ToolResult, ToolRuntime
from harness.policy import PolicyDecision, PolicyEngine, RiskLevel


class EchoTool(BaseTool):
    name = "echo"

    def execute(self, input: dict) -> ToolResult:
        return ToolResult(tool_name=self.name, success=True, output=input.get("message", ""))


class BombTool(BaseTool):
    name = "bomb"

    def execute(self, input: dict) -> ToolResult:
        raise ValueError("boom")


def test_register_and_execute_tool():
    runtime = ToolRuntime()
    runtime.register(EchoTool())
    result = runtime.execute("echo", {"message": "hello"})
    assert result.success is True
    assert result.output == "hello"


def test_execute_unknown_tool_returns_error():
    runtime = ToolRuntime()
    result = runtime.execute("missing", {})
    assert result.success is False
    assert "Unknown tool" in result.error


def test_execute_exception_is_caught():
    runtime = ToolRuntime()
    runtime.register(BombTool())
    result = runtime.execute("bomb", {})
    assert result.success is False
    assert "boom" in result.error


def test_tool_names_lists_registered_tools():
    runtime = ToolRuntime()
    runtime.register(EchoTool())
    assert "echo" in runtime.tool_names


def test_tool_result_policy_record_defaults_to_none():
    result = ToolResult(tool_name="echo", success=True)
    assert result.policy_record is None


def test_high_risk_tool_returns_requires_approval():
    class HighRiskTool(BaseTool):
        name = "high_risk"
        risk_level = RiskLevel.HIGH

        def execute(self, input: dict) -> ToolResult:
            return ToolResult(tool_name=self.name, success=True, output="should not reach here")

    runtime = ToolRuntime(policy_engine=PolicyEngine())
    runtime.register(HighRiskTool())
    result = runtime.execute("high_risk", {})
    assert result.success is False
    assert "requires_approval" in result.error
    assert result.policy_record is not None
    assert result.policy_record.decision == PolicyDecision.ASK_FOR_APPROVAL


def test_critical_risk_tool_is_denied():
    class CriticalTool(BaseTool):
        name = "critical"
        risk_level = RiskLevel.CRITICAL

        def execute(self, input: dict) -> ToolResult:
            return ToolResult(tool_name=self.name, success=True)

    runtime = ToolRuntime(policy_engine=PolicyEngine())
    runtime.register(CriticalTool())
    result = runtime.execute("critical", {})
    assert result.success is False
    assert "policy_denied" in result.error
    assert result.policy_record.decision == PolicyDecision.DENY


def test_low_risk_tool_passes_policy():
    class LowRiskTool(BaseTool):
        name = "low_risk"
        risk_level = RiskLevel.LOW

        def execute(self, input: dict) -> ToolResult:
            return ToolResult(tool_name=self.name, success=True, output="ok")

    runtime = ToolRuntime(policy_engine=PolicyEngine())
    runtime.register(LowRiskTool())
    result = runtime.execute("low_risk", {})
    assert result.success is True
    assert result.output == "ok"
