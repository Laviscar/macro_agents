from __future__ import annotations

from llm.base import LLMMessage, LLMResponse


class FakeLLMClient:
    """Deterministic in-memory client for tests. Pops canned responses or raises a set error."""

    def __init__(self, responses: list[str] | None = None, error: Exception | None = None) -> None:
        self._responses = list(responses or [])
        self._error = error
        self.calls: list[list[LLMMessage]] = []

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        if self._error is not None:
            raise self._error
        text = self._responses.pop(0) if self._responses else "{}"
        return LLMResponse(text=text, input_tokens=10, output_tokens=20)
