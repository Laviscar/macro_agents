from __future__ import annotations

import json

from llm.base import LLMClient, LLMError, LLMMessage
from utils.logger import get_logger


class AuditPanel:
    """0–3 auditor seats critique a judgment over R rounds. Round 1 is independent;
    each later round shows every seat the previous round's critiques. Returns the
    final round's critiques (pure debate — makes no decision). Failing seats are
    skipped with a warning; if no critiques survive, returns []."""

    def __init__(self, seat_clients: list[LLMClient], rounds: int = 1, logger=None) -> None:
        self._seats = list(seat_clients)
        self._rounds = max(1, min(int(rounds), 3))
        self._logger = logger or get_logger("macro_agents.audit")

    @property
    def seat_count(self) -> int:
        return len(self._seats)

    def deliberate(self, judgment: dict, context: str) -> list[str]:
        if not self._seats:
            return []
        prev: list[str] = []
        for round_no in range(1, self._rounds + 1):
            current: list[str] = []
            for index, client in enumerate(self._seats):
                try:
                    current.append(self._critique(client, judgment, context, prev if round_no > 1 else None))
                except (LLMError, ValueError, KeyError, TypeError) as exc:
                    self._logger.warning("audit seat %d failed in round %d: %s", index + 1, round_no, exc)
            prev = current
        return prev

    def _critique(self, client: LLMClient, judgment: dict, context: str, peers: list[str] | None) -> str:
        system = (
            "You are an auditor reviewing a macro narrative manager's judgment about whether "
            "incoming evidence challenges the mainline narrative. Critique it: is the challenge "
            "probability over/under-stated, is opening (or not) a branch justified? Respond with "
            "STRICT JSON only, no prose."
        )
        peer_block = ""
        if peers:
            peer_block = "\nOther auditors said:\n" + "\n".join(f"- {c}" for c in peers) + "\n"
        user = (
            f"Judgment: challenge_probability={judgment['challenge_probability']}, "
            f"open_branch={judgment['open_branch']}\n"
            f"Context:\n{context}\n{peer_block}\n"
            'Return JSON: {"critique": short string, "suggested_probability": 0..1 or null, '
            '"suggested_open_branch": true/false or null}.'
        )
        response = client.complete(
            [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
            temperature=0.0,
            max_tokens=4096,
        )
        data = json.loads(response.text)
        critique = data["critique"]
        if not isinstance(critique, str) or not critique.strip():
            raise ValueError("empty critique")
        return critique.strip()
