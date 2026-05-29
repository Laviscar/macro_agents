import json as _json

import pytest
from harness.budget import BudgetConfig, BudgetGuard
from harness.loop import LoopResult, LoopState, NarrativeLoopEngine
from harness.runtime import ToolResult, ToolRuntime
from harness.session_store import HarnessSessionStore


@pytest.fixture
def store(tmp_path):
    return HarnessSessionStore(tmp_path / "test.sqlite3")


@pytest.fixture
def passing_runtime():
    runtime = ToolRuntime()

    class FakeSortAnalyze:
        name = "sort_and_analyze"
        def execute(self, input):
            return ToolResult(
                tool_name="sort_and_analyze",
                success=True,
                output={"analysis_cards": [], "evidence_list": [], "processed": 0, "skipped": 0},
            )

    class FakeUpdateNarrative:
        name = "update_narrative"
        def execute(self, input):
            return ToolResult(
                tool_name="update_narrative",
                success=True,
                output={"main_narrative_id": "main_default", "branches_count": 0, "commits_count": 0},
            )

    runtime.register(FakeSortAnalyze())
    runtime.register(FakeUpdateNarrative())
    return runtime


@pytest.fixture
def failing_runtime():
    runtime = ToolRuntime()

    class FailingSortAnalyze:
        name = "sort_and_analyze"
        def execute(self, input):
            return ToolResult(tool_name="sort_and_analyze", success=False, error="DB error")

    runtime.register(FailingSortAnalyze())
    return runtime


def test_successful_run_returns_done(store, passing_runtime):
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=passing_runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    result = engine.run(session_id=session_id, news_item_ids=[1, 2])
    assert result.final_state == LoopState.DONE
    assert result.stop_reason == "task_complete"
    assert result.events_count > 0


def test_tool_failure_transitions_to_failed(store, failing_runtime):
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=failing_runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    result = engine.run(session_id=session_id, news_item_ids=[1])
    assert result.final_state == LoopState.FAILED
    assert result.stop_reason is not None


def test_events_recorded_to_session_store(store, passing_runtime):
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=passing_runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    engine.run(session_id=session_id, news_item_ids=[])
    events = store.list_events_for_session(session_id)
    event_types = [e["event_type"] for e in events]
    assert "session_started" in event_types
    assert "loop_transition" in event_types
    assert "session_completed" in event_types


def test_time_budget_exceeded_still_completes(store, passing_runtime):
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=0.0))
    engine = NarrativeLoopEngine(runtime=passing_runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    result = engine.run(session_id=session_id, news_item_ids=[])
    assert result.final_state == LoopState.DONE
    assert result.stop_reason == "time_exceeded"


def test_session_marked_completed_after_successful_run(store, passing_runtime):
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=passing_runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    engine.run(session_id=session_id, news_item_ids=[])
    sessions = store.list_sessions()
    assert sessions[0]["status"] == "completed"


def test_session_marked_failed_on_tool_error(store, failing_runtime):
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=failing_runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    engine.run(session_id=session_id, news_item_ids=[1])
    sessions = store.list_sessions()
    assert sessions[0]["status"] == "failed"


def test_update_narrative_failure_transitions_to_failed(store):
    runtime = ToolRuntime()

    class OkSortAnalyze:
        name = "sort_and_analyze"
        def execute(self, input):
            return ToolResult(
                tool_name="sort_and_analyze",
                success=True,
                output={"analysis_cards": [], "evidence_list": [], "processed": 0, "skipped": 0},
            )

    class FailingUpdateNarrative:
        name = "update_narrative"
        def execute(self, input):
            return ToolResult(tool_name="update_narrative", success=False, error="write error")

    runtime.register(OkSortAnalyze())
    runtime.register(FailingUpdateNarrative())
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    result = engine.run(session_id=session_id, news_item_ids=[1])
    assert result.final_state == LoopState.FAILED
    assert "update_narrative" in result.stop_reason


def test_plan_sets_planned_tools_when_news_items_present(store, passing_runtime):
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=passing_runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    result = engine.run(session_id=session_id, news_item_ids=[1, 2, 3])
    events = store.list_events_for_session(session_id)
    plan_events = [e for e in events if e["event_type"] == "plan_decided"]
    assert len(plan_events) == 1
    payload = _json.loads(plan_events[0]["payload_json"])
    assert "sort_and_analyze" in payload["planned_tools"]
    assert result.final_state == LoopState.DONE


def test_plan_sets_empty_tools_when_no_news_items(store, passing_runtime):
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=passing_runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    engine.run(session_id=session_id, news_item_ids=[])
    events = store.list_events_for_session(session_id)
    plan_events = [e for e in events if e["event_type"] == "plan_decided"]
    assert len(plan_events) == 1
    payload = _json.loads(plan_events[0]["payload_json"])
    assert payload["planned_tools"] == []


def test_empty_plan_skips_tool_exec_and_still_completes(store, passing_runtime):
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=passing_runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    result = engine.run(session_id=session_id, news_item_ids=[])
    assert result.final_state == LoopState.DONE
    events = store.list_events_for_session(session_id)
    tool_calls = [e for e in events if e["event_type"] == "tool_call"]
    assert len(tool_calls) == 0


def test_observe_emits_observe_result_event(store, passing_runtime):
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=passing_runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    engine.run(session_id=session_id, news_item_ids=[1])
    events = store.list_events_for_session(session_id)
    observe_events = [e for e in events if e["event_type"] == "observe_result"]
    assert len(observe_events) == 1


def test_observe_sets_all_skipped_when_no_evidence_produced(store):
    from harness.runtime import ToolRuntime, ToolResult
    from harness.policy import RiskLevel

    class NoEvidenceTool:
        name = "sort_and_analyze"
        risk_level = RiskLevel.LOW
        is_concurrency_safe = True
        def execute(self, input):
            return ToolResult(
                tool_name="sort_and_analyze",
                success=True,
                output={"analysis_cards": [], "evidence_list": [], "processed": 2, "skipped": 2},
            )

    class UpdateTool:
        name = "update_narrative"
        risk_level = RiskLevel.MEDIUM
        is_concurrency_safe = False
        def execute(self, input):
            return ToolResult(tool_name="update_narrative", success=True, output={"main_narrative_id": "x"})

    runtime = ToolRuntime()
    runtime.register(NoEvidenceTool())
    runtime.register(UpdateTool())
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    engine.run(session_id=session_id, news_item_ids=[1, 2])
    events = store.list_events_for_session(session_id)
    observe_events = [e for e in events if e["event_type"] == "observe_result"]
    assert _json.loads(observe_events[0]["payload_json"])["all_skipped"] is True


def test_observe_all_skipped_skips_update_narrative(store):
    from harness.runtime import ToolRuntime, ToolResult
    from harness.policy import RiskLevel

    update_called = []

    class NoEvidenceTool:
        name = "sort_and_analyze"
        risk_level = RiskLevel.LOW
        is_concurrency_safe = True
        def execute(self, input):
            return ToolResult(
                tool_name="sort_and_analyze",
                success=True,
                output={"analysis_cards": [], "evidence_list": [], "processed": 1, "skipped": 1},
            )

    class TrackingUpdateTool:
        name = "update_narrative"
        risk_level = RiskLevel.MEDIUM
        is_concurrency_safe = False
        def execute(self, input):
            update_called.append(True)
            return ToolResult(tool_name="update_narrative", success=True, output={})

    runtime = ToolRuntime()
    runtime.register(NoEvidenceTool())
    runtime.register(TrackingUpdateTool())
    budget = BudgetGuard(BudgetConfig(time_budget_seconds=60.0))
    engine = NarrativeLoopEngine(runtime=runtime, session_store=store, budget=budget)
    session_id = store.create_session()
    engine.run(session_id=session_id, news_item_ids=[1])
    assert len(update_called) == 0
