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

    def execute_batch(self, calls: list[tuple[str, dict]]) -> list[ToolResult]:
        """Execute multiple tools. Concurrent-safe tools run in parallel; others run serially after.

        Returns results in the same order as calls.
        """
        import concurrent.futures

        safe: list[tuple[int, str, dict]] = []
        unsafe: list[tuple[int, str, dict]] = []

        for i, (name, inp) in enumerate(calls):
            tool = self._tools.get(name)
            if tool is not None and tool.is_concurrency_safe:
                safe.append((i, name, inp))
            else:
                unsafe.append((i, name, inp))

        result_map: dict[int, ToolResult] = {}

        if safe:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(safe)) as pool:
                future_to_idx = {
                    pool.submit(self.execute, name, inp): idx
                    for idx, name, inp in safe
                }
                for future in concurrent.futures.as_completed(future_to_idx):
                    result_map[future_to_idx[future]] = future.result()

        for idx, name, inp in unsafe:
            result_map[idx] = self.execute(name, inp)

        return [result_map[i] for i in range(len(calls))]
