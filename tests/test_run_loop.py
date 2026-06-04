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


def test_run_once_returns_per_stage_results():
    loop = RunLoop([
        Stage("a", interval_seconds=10, run_fn=lambda: {"n": 1}),
        Stage("b", interval_seconds=10, run_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom"))),
    ])
    results = loop.run_once()
    assert results[0] == {"stage": "a", "ok": True, "result": {"n": 1}}
    assert results[1]["stage"] == "b" and results[1]["ok"] is False and "boom" in results[1]["error"]


def test_build_run_loop_audit_seats(monkeypatch):
    import run_loop
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("NARRATIVE_AUDIT_SEATS", "2")
    monkeypatch.setenv("NARRATIVE_AUDIT_ROUNDS", "2")
    run_loop.build_run_loop()
    nm = run_loop._last_narrative_manager
    assert nm.audit_panel is not None and nm.audit_panel.seat_count == 2


def test_build_run_loop_no_audit_by_default(monkeypatch):
    import run_loop
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("NARRATIVE_AUDIT_SEATS", raising=False)
    run_loop.build_run_loop()
    assert run_loop._last_narrative_manager.audit_panel is None


def test_build_run_loop_has_fred_stage(monkeypatch):
    import run_loop
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    loop = run_loop.build_run_loop()
    assert any(s.name == "fred" for s in loop.stages)
