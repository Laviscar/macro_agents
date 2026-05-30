import pytest
from run_loop import Stage, RunLoop


def test_stage_runs_only_when_due():
    calls = []
    loop = RunLoop([Stage("a", interval_seconds=100, run_fn=lambda: calls.append("a"))])
    loop.tick(now=0.0)      # first tick always runs (never run before)
    loop.tick(now=50.0)     # not due yet
    loop.tick(now=100.0)    # due again
    assert calls == ["a", "a"]


def test_stages_run_in_order_when_due():
    order = []
    loop = RunLoop([
        Stage("first", interval_seconds=10, run_fn=lambda: order.append("first")),
        Stage("second", interval_seconds=10, run_fn=lambda: order.append("second")),
    ])
    loop.tick(now=0.0)
    assert order == ["first", "second"]


def test_one_stage_failure_does_not_stop_others():
    ran = []
    def boom():
        raise RuntimeError("stage failed")
    loop = RunLoop([
        Stage("bad", interval_seconds=10, run_fn=boom),
        Stage("good", interval_seconds=10, run_fn=lambda: ran.append("good")),
    ])
    loop.tick(now=0.0)  # must not raise
    assert ran == ["good"]


def test_run_once_runs_all_stages_regardless_of_interval():
    ran = []
    loop = RunLoop([Stage("a", interval_seconds=99999, run_fn=lambda: ran.append("a"))])
    loop.run_once()
    assert ran == ["a"]
