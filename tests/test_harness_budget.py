import time
from harness.budget import BudgetConfig, BudgetGuard


def test_budget_ok_when_within_limits():
    guard = BudgetGuard(BudgetConfig(time_budget_seconds=60.0, token_budget=0))
    status = guard.check()
    assert status.ok is True
    assert status.reason is None
    assert status.elapsed_seconds >= 0.0
    assert status.tokens_used == 0


def test_budget_exceeded_when_time_runs_out():
    guard = BudgetGuard(BudgetConfig(time_budget_seconds=0.01, token_budget=0))
    time.sleep(0.02)
    status = guard.check()
    assert status.ok is False
    assert status.reason == "time_exceeded"


def test_budget_exceeded_when_tokens_hit_limit():
    guard = BudgetGuard(BudgetConfig(time_budget_seconds=60.0, token_budget=100))
    guard.add_tokens(100)
    status = guard.check()
    assert status.ok is False
    assert status.reason == "token_exceeded"
    assert status.tokens_used == 100


def test_token_budget_zero_means_no_token_limit():
    guard = BudgetGuard(BudgetConfig(time_budget_seconds=60.0, token_budget=0))
    guard.add_tokens(999_999)
    status = guard.check()
    assert status.ok is True
