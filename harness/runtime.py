from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None


class BaseTool(ABC):
    name: str

    @abstractmethod
    def execute(self, input: dict) -> ToolResult: ...


class ToolRuntime:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def execute(self, tool_name: str, input: dict) -> ToolResult:
        if tool_name not in self._tools:
            return ToolResult(tool_name=tool_name, success=False, error=f"Unknown tool: {tool_name}")
        try:
            return self._tools[tool_name].execute(input)
        except Exception as exc:
            return ToolResult(tool_name=tool_name, success=False, error=str(exc))

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
