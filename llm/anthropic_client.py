from __future__ import annotations

import json

from llm._transport import TransportFn, urllib_transport
from llm.base import LLMError, LLMMessage, LLMResponse
from llm.config import LLMConfig


class AnthropicClient:
    """Claude Messages API client. Same LLMClient protocol as the OpenAI-compatible one."""

    def __init__(self, config: LLMConfig, transport: TransportFn | None = None) -> None:
        self._config = config
        self._transport = transport or urllib_transport

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        if not self._config.api_key:
            raise LLMError("LLM api key is not configured")

        system = "\n".join(m.content for m in messages if m.role == "system")
        chat = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]
        url = f"{self._config.base_url.rstrip('/')}/messages"
        headers = {
            "x-api-key": self._config.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat,
        }
        if system:
            payload["system"] = system
        body = json.dumps(payload).encode("utf-8")

        try:
            data = self._transport(url, headers, body, self._config.timeout_seconds)
        except Exception as exc:
            raise LLMError(f"transport failure: {exc}") from exc

        try:
            text = data["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {exc}") from exc

        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        return LLMResponse(
            text=text,
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            raw=data,
        )
