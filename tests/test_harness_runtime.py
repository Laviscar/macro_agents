from harness.runtime import BaseTool, ToolResult, ToolRuntime


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
