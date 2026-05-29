from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from harness.policy import PolicyRecord

from harness.policy import PolicyDecision, PolicyEngine, RiskLevel


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None
    policy_record: "PolicyRecord | None" = None


class BaseTool(ABC):
    name: str
    risk_level: RiskLevel = RiskLevel.LOW
    is_concurrency_safe: bool = True

    @abstractmethod
    def execute(self, input: dict) -> ToolResult: ...


class ToolRuntime:
    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._policy_engine = policy_engine

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def execute(self, tool_name: str, input: dict) -> ToolResult:
        if tool_name not in self._tools:
            return ToolResult(tool_name=tool_name, success=False, error=f"Unknown tool: {tool_name}")
        tool = self._tools[tool_name]
        if self._policy_engine is not None:
            record = self._policy_engine.record(tool.name, tool.risk_level)
            if record.decision == PolicyDecision.DENY:
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"policy_denied: {record.reason}",
                    policy_record=record,
                )
            if record.decision == PolicyDecision.ASK_FOR_APPROVAL:
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"requires_approval: {record.reason}",
                    policy_record=record,
                )
        try:
            return self._tools[tool_name].execute(input)
        except Exception as exc:
            return ToolResult(tool_name=tool_name, success=False, error=str(exc))

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
