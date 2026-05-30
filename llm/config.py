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


def load_llm_config(env: dict | None = None, tier: str | None = None) -> LLMConfig:
    """Build LLMConfig from environment. With `tier` (e.g. "triage"/"analysis"),
    `LLM_<TIER>_X` is read first, falling back to bare `LLM_X`. No secrets hard-coded.
    """
    env = env if env is not None else os.environ

    def g(key: str) -> str | None:
        if tier:
            v = env.get(f"LLM_{tier.upper()}_{key}")
            if v:
                return v
        return env.get(f"LLM_{key}")

    provider = (g("PROVIDER") or "openai").lower()
    model = g("MODEL") or _DEFAULT_MODEL.get(provider, "")
    base_url = g("BASE_URL") or _DEFAULT_BASE_URL.get(provider, "")
    key_env = g("API_KEY_ENV") or _DEFAULT_KEY_ENV.get(provider, "LLM_API_KEY")
    api_key = env.get(key_env) or g("API_KEY")
    try:
        timeout = float(g("TIMEOUT_SECONDS") or 30.0)
    except ValueError:
        timeout = 30.0
    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=timeout,
    )
