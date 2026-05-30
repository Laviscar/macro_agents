from __future__ import annotations

from llm.base import LLMClient, LLMMessage, LLMResponse


class TokenMeter:
    """Accumulates token usage across LLM calls. drain() returns the running total and resets it."""

    def __init__(self) -> None:
        self._total = 0

    @property
    def total(self) -> int:
        return self._total

    def add(self, count: int) -> None:
        self._total += int(count or 0)

    def drain(self) -> int:
        value = self._total
        self._total = 0
        return value

    def reset(self) -> None:
        self._total = 0


class MeteredLLMClient:
    """Wraps any LLMClient; records input+output tokens of each response into a TokenMeter."""

    def __init__(self, inner: LLMClient, meter: TokenMeter) -> None:
        self._inner = inner
        self._meter = meter

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        response = self._inner.complete(messages, temperature=temperature, max_tokens=max_tokens)
        self._meter.add(response.input_tokens + response.output_tokens)
        return response
