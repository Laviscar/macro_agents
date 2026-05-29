from __future__ import annotations

from llm.anthropic_client import AnthropicClient
from llm.base import LLMClient
from llm.config import LLMConfig
from llm.openai_compatible import OpenAICompatibleClient, TransportFn


def build_llm_client(config: LLMConfig, transport: "TransportFn | None" = None) -> LLMClient | None:
    """Return a client for the configured provider, or None if unconfigured/unknown."""
    if not config.is_configured:
        return None
    if config.provider in ("openai", "minimax"):
        return OpenAICompatibleClient(config, transport=transport)
    if config.provider == "anthropic":
        return AnthropicClient(config, transport=transport)
    return None
