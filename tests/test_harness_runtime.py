import time

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


def test_execute_batch_returns_results_in_call_order():
    runtime = ToolRuntime()
    runtime.register(EchoTool())
    results = runtime.execute_batch([("echo", {"message": "a"}), ("echo", {"message": "b"})])
    assert len(results) == 2
    assert results[0].output == "a"
    assert results[1].output == "b"


def test_execute_batch_runs_safe_tools_faster_than_serial():
    class SlowSafeTool(BaseTool):
        name = "slow_safe"
        is_concurrency_safe = True

        def execute(self, input: dict) -> ToolResult:
            time.sleep(0.05)
            return ToolResult(tool_name=self.name, success=True, output=input.get("id"))

    runtime = ToolRuntime()
    runtime.register(SlowSafeTool())

    start = time.monotonic()
    results = runtime.execute_batch([
        ("slow_safe", {"id": 1}),
        ("slow_safe", {"id": 2}),
        ("slow_safe", {"id": 3}),
    ])
    elapsed = time.monotonic() - start

    assert all(r.success for r in results)
    assert elapsed < 0.12  # 3x0.05s serial = 0.15s; parallel ~0.05s


def test_execute_batch_runs_unsafe_tools_serially():
    execution_order: list[str] = []

    class TrackingTool(BaseTool):
        is_concurrency_safe = False

        def __init__(self, tool_name: str) -> None:
            self.name = tool_name

        def execute(self, input: dict) -> ToolResult:
            execution_order.append(self.name)
            return ToolResult(tool_name=self.name, success=True)

    runtime = ToolRuntime()
    runtime.register(TrackingTool("first"))
    runtime.register(TrackingTool("second"))
    runtime.execute_batch([("first", {}), ("second", {})])
    assert execution_order == ["first", "second"]


def test_allow_tool_attaches_policy_record():
    class MediumWriteTool(BaseTool):
        name = "medium_write"
        risk_level = RiskLevel.MEDIUM

        def execute(self, input: dict) -> ToolResult:
            return ToolResult(tool_name=self.name, success=True, output="written")

    runtime = ToolRuntime(policy_engine=PolicyEngine())
    runtime.register(MediumWriteTool())
    result = runtime.execute("medium_write", {})
    assert result.success is True
    assert result.policy_record is not None
    assert result.policy_record.decision == PolicyDecision.ALLOW


def test_no_policy_engine_leaves_record_none():
    class PlainTool(BaseTool):
        name = "plain"

        def execute(self, input: dict) -> ToolResult:
            return ToolResult(tool_name=self.name, success=True)

    runtime = ToolRuntime()  # no policy engine
    runtime.register(PlainTool())
    result = runtime.execute("plain", {})
    assert result.policy_record is None
