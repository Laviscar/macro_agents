from __future__ import annotations

import json

from llm.base import LLMClient, LLMError, LLMMessage
from schemas.resource_card import ResourceCard
from utils.logger import get_logger, log_event


class TriageAgent:
    """Cheap-LLM importance screen. Degrades to the reasoning client (with a warning)
    when the cheap client fails, and fails open (important=True) if both fail."""

    def __init__(
        self,
        primary_client: LLMClient | None = None,
        fallback_client: LLMClient | None = None,
        logger=None,
    ) -> None:
        self._primary = primary_client
        self._fallback = fallback_client
        self._logger = logger or get_logger("macro_agents.triage")
        self.degraded_count = 0

    def is_important(self, resource_card: ResourceCard) -> bool:
        messages = self._build_messages(resource_card)
        if self._primary is not None:
            try:
                return self._judge(self._primary, messages)
            except (LLMError, ValueError, KeyError, TypeError):
                pass
        if self._fallback is not None:
            try:
                result = self._judge(self._fallback, messages)
                self.degraded_count += 1
                self._logger.warning(
                    "triage degraded to fallback: primary triage client failed; "
                    "used reasoning client"
                )
                log_event(
                    self._logger, "triage_degraded_to_fallback",
                    reason="primary triage client failed; used reasoning client",
                    title=resource_card.title[:80],
                )
                return result
            except (LLMError, ValueError, KeyError, TypeError):
                pass
        # fail open — never silently drop news
        return True

    def _judge(self, client: LLMClient, messages: list[LLMMessage]) -> bool:
        response = client.complete(messages, temperature=0.0, max_tokens=4096)
        data = json.loads(response.text)
        important = data["important"]
        if not isinstance(important, bool):
            raise ValueError("important must be a boolean")
        return important

    def _build_messages(self, resource_card: ResourceCard) -> list[LLMMessage]:
        system = (
            "You screen macro news for a research system. Decide if an item is important "
            "enough to deeply analyze. Bias toward keeping anything macro-relevant (policy, "
            "inflation, rates, growth, geopolitics, energy, FX, systemic risk). Respond with "
            "STRICT JSON only."
        )
        user = (
            f"Title: {resource_card.title}\n"
            f"Summary: {resource_card.one_liner}\n"
            f"Themes: {', '.join(resource_card.theme)}\n\n"
            'Return JSON: {"important": boolean, "reason": short string}.'
        )
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]
