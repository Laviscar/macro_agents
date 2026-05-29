import json
import pytest
from harness.coordinator import HarnessCoordinator, TaskInput
from harness.loop import LoopState
from repositories.news_repository import SQLiteNewsRepository
from schemas.raw_news_item import RawNewsItem
from utils.clock import now_iso


def _make_item(title: str, source: str = "test") -> RawNewsItem:
    return RawNewsItem(
        source_type="rss",
        source_name=source,
        external_id=title,
        url=f"https://example.com/{title}",
        title=title,
        summary="test summary about inflation data",
        published_at=now_iso(),
        fetched_at=now_iso(),
        raw_payload={},
    )


@pytest.fixture
def coordinator(tmp_path):
    return HarnessCoordinator(
        db_path=tmp_path / "test.sqlite3",
        storage_root=tmp_path / "storage",
    )


def test_run_task_with_empty_ids_returns_done(coordinator):
    result = coordinator.run_task(TaskInput(news_item_ids=[]))
    assert result.final_state == LoopState.DONE
    assert result.stop_reason == "task_complete"


def test_run_task_with_news_items_returns_done(coordinator, tmp_path):
    repo = SQLiteNewsRepository(tmp_path / "test.sqlite3")
    nid = repo.insert_news_item(_make_item("Inflation cools lower than expected"))
    result = coordinator.run_task(TaskInput(news_item_ids=[nid]))
    assert result.final_state == LoopState.DONE


def test_run_task_creates_session_in_store(coordinator):
    result = coordinator.run_task(TaskInput(news_item_ids=[], task_description="test run"))
    sessions = coordinator.session_store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["id"] == result.session_id
    assert sessions[0]["status"] == "completed"


def test_run_task_events_are_replayable(coordinator):
    result = coordinator.run_task(TaskInput(news_item_ids=[]))
    events = coordinator.session_store.list_events_for_session(result.session_id)
    assert len(events) > 0
    event_types = {e["event_type"] for e in events}
    assert "session_started" in event_types
    assert "loop_transition" in event_types
    assert "session_completed" in event_types


def test_run_pending_with_no_pending_items(coordinator):
    result = coordinator.run_pending()
    assert result.final_state == LoopState.DONE


def test_run_pending_processes_pending_news(coordinator, tmp_path):
    repo = SQLiteNewsRepository(tmp_path / "test.sqlite3")
    for title in ["GDP surprise beats expectations", "Trade deficit widens more than expected"]:
        repo.insert_news_item(_make_item(title))
    result = coordinator.run_pending(limit=10)
    assert result.final_state == LoopState.DONE
    events = coordinator.session_store.list_events_for_session(result.session_id)
    tool_call_events = [e for e in events if e["event_type"] == "tool_call"]
    assert len(tool_call_events) >= 1  # sort_and_analyze was called
