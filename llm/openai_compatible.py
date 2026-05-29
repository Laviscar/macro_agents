from __future__ import annotations

import json
import urllib.request
from typing import Callable

from llm.base import LLMError, LLMMessage, LLMResponse
from llm.config import LLMConfig

# transport(url, headers, body_bytes, timeout) -> parsed json dict
TransportFn = Callable[[str, dict, bytes, float], dict]


def _urllib_transport(url: str, headers: dict, body: bytes, timeout: float) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


class OpenAICompatibleClient:
    """Chat-completions client for OpenAI-compatible endpoints (OpenAI, MiniMax, proxies)."""

    def __init__(self, config: LLMConfig, transport: TransportFn | None = None) -> None:
        self._config = config
        self._transport = transport or _urllib_transport

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        if not self._config.api_key:
            raise LLMError("LLM api key is not configured")

        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        body = json.dumps(payload).encode("utf-8")

        try:
            data = self._transport(url, headers, body, self._config.timeout_seconds)
        except Exception as exc:  # network/timeout/etc.
            raise LLMError(f"transport failure: {exc}") from exc

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {exc}") from exc

        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        return LLMResponse(
            text=text,
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            raw=data,
        )
