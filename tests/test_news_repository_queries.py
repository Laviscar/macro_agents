import pytest
from repositories.news_repository import SQLiteNewsRepository
from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence
from schemas.raw_news_item import RawNewsItem
from utils.clock import now_iso


def _repo(tmp_path):
    return SQLiteNewsRepository(tmp_path / "t.sqlite3")


def _item(title):
    return RawNewsItem(source_type="rss", source_name="s", external_id=title, url=f"https://x/{title}",
                       title=title, summary="s", published_at=now_iso(), fetched_at=now_iso(), raw_payload={})


def _card(cid, created_at):
    return AnalysisCard(id=cid, event_id="e", source_card_ids=["e"], reframed_question="q",
                        signal_level="structure", thesis="t", evidence_for=["x"], evidence_against=[],
                        macro_variables=["m"], asset_mapping=[], confidence=0.6, mainline_relation="supports",
                        candidate_branch_title=None, invalidation_conditions=[], created_at=created_at)


def _ev(eid, cid, created_at):
    return Evidence(id=eid, source_analysis_id=cid, source_card_ids=["e"], claim="c", relation_type="supports",
                    target_main_narrative_id="main_default", target_branch_id=None, strength=0.6, confidence=0.6,
                    why="w", counter_evidence=[], created_at=created_at)


def test_list_news_by_status(tmp_path):
    repo = _repo(tmp_path)
    repo.insert_news_item(_item("a"))
    rows = repo.list_news_by_status("pending_sort", limit=10)
    assert len(rows) == 1 and rows[0]["analysis_status"] == "pending_sort"
    assert repo.list_news_by_status("analyzed", limit=10) == []


def test_get_evidence_and_cards_since(tmp_path):
    repo = _repo(tmp_path)
    nid = repo.insert_news_item(_item("a"))
    repo.save_analysis_bundle(nid, _card("ac_old", "2026-05-30T10:00:00Z"), [_ev("ev_old", "ac_old", "2026-05-30T10:00:00Z")])
    repo.save_analysis_bundle(nid, _card("ac_new", "2026-05-31T10:00:00Z"), [_ev("ev_new", "ac_new", "2026-05-31T10:00:00Z")])
    ev = repo.get_evidence_since("2026-05-31T00:00:00Z")
    assert [e.id for e in ev] == ["ev_new"]
    cards = repo.get_analysis_cards_since("2026-05-31T00:00:00Z")
    assert [c.id for c in cards] == ["ac_new"]
    assert repo.get_evidence_since("2020-01-01T00:00:00Z")  # both
