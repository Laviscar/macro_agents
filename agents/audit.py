from __future__ import annotations

import json
from typing import Callable

from llm.base import LLMClient, LLMError, LLMMessage
from utils.logger import get_logger

# rejudge(judgment, critiques, context) -> revised judgment dict
RejudgeFn = Callable[[dict, list[str], str], dict]


class AuditPanel:
    """0–3 auditor seats critique a narrative-manager judgment, then the manager
    re-judges. Two debate modes (configurable):

    - "cross" (cross-validation): seats critique over R rounds, each later round seeing
      the previous round's peer critiques; the manager re-judges ONCE at the end.
    - "p2p" (point-to-point): seats never see each other; each of R rounds every seat
      critiques the CURRENT judgment and the manager re-judges — an X-round dialogue with
      the manager as the hub.

    `run()` returns the final judgment dict. Failing seats are skipped with a warning;
    if no critiques survive a round, the judgment is left unchanged.
    """

    def __init__(self, seat_clients: list[LLMClient], rounds: int = 1, mode: str = "cross", logger=None) -> None:
        self._seats = list(seat_clients)
        self._rounds = max(1, min(int(rounds), 3))
        self._mode = mode if mode in ("cross", "p2p") else "cross"
        self._logger = logger or get_logger("macro_agents.audit")

    @property
    def seat_count(self) -> int:
        return len(self._seats)

    @property
    def mode(self) -> str:
        return self._mode

    def run(self, judgment: dict, context: str, rejudge: RejudgeFn) -> dict:
        """Orchestrate the debate and return the final judgment dict."""
        if not self._seats:
            return judgment

        if self._mode == "p2p":
            current = dict(judgment)
            for _ in range(self._rounds):
                critiques = self._critique_round(current, context, peers=None)
                if not critiques:
                    break
                current = rejudge(current, critiques, context)  # manager revises every round
            return current

        # cross: seats refine among themselves over R rounds, manager concludes once
        prev: list[str] = []
        for round_no in range(1, self._rounds + 1):
            prev = self._critique_round(judgment, context, peers=prev if round_no > 1 else None)
        if not prev:
            return judgment
        return rejudge(judgment, prev, context)

    def _critique_round(self, judgment: dict, context: str, peers: list[str] | None) -> list[str]:
        critiques: list[str] = []
        for index, client in enumerate(self._seats):
            try:
                critiques.append(self._critique(client, judgment, context, peers))
            except (LLMError, ValueError, KeyError, TypeError) as exc:
                self._logger.warning("audit seat %d failed: %s", index + 1, exc)
        return critiques

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
