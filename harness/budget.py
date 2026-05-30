from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal


@dataclass
class BudgetConfig:
    time_budget_seconds: float = 300.0
    token_budget: int = 0  # 0 = no token limit; >0 enforced once real LLM tokens are metered in


@dataclass(frozen=True)
class BudgetStatus:
    ok: bool
    reason: Literal["time_exceeded", "token_exceeded"] | None
    elapsed_seconds: float
    tokens_used: int


class BudgetGuard:
    """One instance per task session — _start_time is set at construction and never reset."""
    def __init__(self, config: BudgetConfig) -> None:
        self.config = config
        self.tokens_used: int = 0
        self._start_time: float = time.monotonic()

    def add_tokens(self, count: int) -> None:
        self.tokens_used += count

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start_time

    def check(self) -> BudgetStatus:
        elapsed = self.elapsed_seconds
        if elapsed >= self.config.time_budget_seconds:
            return BudgetStatus(ok=False, reason="time_exceeded", elapsed_seconds=elapsed, tokens_used=self.tokens_used)
        if self.config.token_budget > 0 and self.tokens_used >= self.config.token_budget:
            return BudgetStatus(ok=False, reason="token_exceeded", elapsed_seconds=elapsed, tokens_used=self.tokens_used)
        return BudgetStatus(ok=True, reason=None, elapsed_seconds=elapsed, tokens_used=self.tokens_used)
