import json
import pytest
from agents.analyst import AnalystAgent
from agents.news_sorter import NewsSorterAgent
from agents.narrative_manager import NarrativeManagerAgent
from agents.triage import TriageAgent
from llm.fake import FakeLLMClient
from pipelines.stages import triage_pending, analyze_pending, consolidate
from repositories.news_repository import SQLiteNewsRepository
from schemas.raw_news_item import RawNewsItem
from utils.clock import now_iso


def _item(title):
    return RawNewsItem(source_type="rss", source_name="s", external_id=title, url=f"https://x/{title}",
                       title=title, summary="inflation cooled again", published_at=now_iso(),
                       fetched_at=now_iso(), raw_payload={})


def test_triage_routes_important_and_skips(tmp_path):
    repo = SQLiteNewsRepository(tmp_path / "t.sqlite3")
    repo.insert_news_item(_item("keep me"))
    repo.insert_news_item(_item("drop me"))
    primary = FakeLLMClient(responses=[
        json.dumps({"important": True, "reason": "x"}),
        json.dumps({"important": False, "reason": "y"}),
    ])
    triage = TriageAgent(primary_client=primary)
    result = triage_pending(repo, triage, NewsSorterAgent(), limit=10)
    assert result["important"] == 1 and result["skipped"] == 1
    assert len(repo.list_news_by_status("pending_analysis", 10)) == 1
    assert len(repo.list_news_by_status("skipped", 10)) == 1


def test_analyze_pending_produces_evidence(tmp_path):
    repo = SQLiteNewsRepository(tmp_path / "t.sqlite3")
    repo.insert_news_item(_item("inflation cools"))
    triage_pending(repo, TriageAgent(primary_client=None), NewsSorterAgent(), limit=10)  # fail-open → pending_analysis
    result = analyze_pending(repo, AnalystAgent(), limit=10)  # no llm → rule analysis
    assert result["analyzed"] >= 1
    assert len(repo.list_news_by_status("analyzed", 10)) >= 1
    assert repo.count_evidence_records() >= 1


def test_consolidate_uses_watermark(tmp_path):
    repo = SQLiteNewsRepository(tmp_path / "t.sqlite3")
    repo.insert_news_item(_item("inflation cools lower than expected"))
    triage_pending(repo, TriageAgent(primary_client=None), NewsSorterAgent(), limit=10)
    analyze_pending(repo, AnalystAgent(), limit=10)
    storage = tmp_path / "storage"
    run_state = storage / "run_state.json"
    first = consolidate(repo, NarrativeManagerAgent(), storage, run_state)
    assert first["consolidated_evidence"] >= 1
    assert list((storage / "main_narrative_state").glob("*.json"))
    second = consolidate(repo, NarrativeManagerAgent(), storage, run_state)
    assert second["consolidated_evidence"] == 0  # nothing new since watermark
