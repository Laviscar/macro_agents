from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
_DEFAULT_BASE_URL = {
    "openai": "https://api.openai.com/v1",
    "minimax": "https://api.minimax.chat/v1",
    "anthropic": "https://api.anthropic.com/v1",
}
_DEFAULT_MODEL = {
    "openai": "gpt-4o-mini",
    "minimax": "abab6.5s-chat",
    "anthropic": "claude-sonnet-4-6",
}


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str | None
    base_url: str
    timeout_seconds: float = 30.0

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


def load_llm_config(env: dict | None = None) -> LLMConfig:
    """Build LLMConfig from environment. No secrets are ever hard-coded.

    Recognized env vars:
      LLM_PROVIDER (openai|minimax|anthropic; default openai)
      LLM_MODEL, LLM_BASE_URL, LLM_TIMEOUT_SECONDS (optional overrides)
      LLM_API_KEY_ENV (name of the var holding the key; default per provider)
      LLM_API_KEY (fallback key var)
    """
    env = env if env is not None else os.environ
    provider = (env.get("LLM_PROVIDER") or "openai").lower()
    model = env.get("LLM_MODEL") or _DEFAULT_MODEL.get(provider, "")
    base_url = env.get("LLM_BASE_URL") or _DEFAULT_BASE_URL.get(provider, "")
    key_env = env.get("LLM_API_KEY_ENV") or _DEFAULT_KEY_ENV.get(provider, "LLM_API_KEY")
    api_key = env.get(key_env) or env.get("LLM_API_KEY")
    try:
        timeout = float(env.get("LLM_TIMEOUT_SECONDS") or 30.0)
    except ValueError:
        timeout = 30.0
    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=timeout,
    )
