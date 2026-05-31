import json
from pathlib import Path
from presenters.research_presenter import build_research_overview
from repositories.news_repository import SQLiteNewsRepository
from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence
from schemas.raw_news_item import RawNewsItem
from utils.clock import now_iso


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_reinforcing_factors_resolve_to_claim_text(tmp_path):
    repo = SQLiteNewsRepository(tmp_path / "t.sqlite3")
    nid = repo.insert_news_item(RawNewsItem(source_type="rss", source_name="s", external_id="a",
        url="https://x/a", title="t", summary="s", published_at=now_iso(), fetched_at=now_iso(), raw_payload={}))
    card = AnalysisCard(id="ac1", event_id="e", source_card_ids=["e"], reframed_question="q",
        signal_level="structure", thesis="t", evidence_for=["x"], evidence_against=[], macro_variables=["m"],
        asset_mapping=[], confidence=0.6, mainline_relation="supports", candidate_branch_title=None,
        invalidation_conditions=[], created_at=now_iso())
    ev = Evidence(id="ev_keep", source_analysis_id="ac1", source_card_ids=["e"], claim="通胀降温支撑软着陆",
        relation_type="supports", target_main_narrative_id="main_default", target_branch_id=None,
        strength=0.6, confidence=0.6, why="w", counter_evidence=[], created_at=now_iso())
    repo.save_analysis_bundle(nid, card, [ev])
    _write(tmp_path / "main_narrative_state" / "main_default.json", {
        "id": "main_default", "title": "主线", "status": "active", "strength": 0.6, "confidence": 0.6,
        "supporting_evidence": ["ev_keep"], "fragility": [], "watch_items": [], "updated_at": now_iso()})
    o = build_research_overview(tmp_path, repo)
    assert o.main_cards[0].reinforcing_factors == ["通胀降温支撑软着陆"]  # claim text, not "ev_keep"


def test_reinforcing_factors_fallback_to_ids_without_repo(tmp_path):
    _write(tmp_path / "main_narrative_state" / "main_default.json", {
        "id": "main_default", "title": "主线", "status": "active", "strength": 0.6, "confidence": 0.6,
        "supporting_evidence": ["ev_1", "ev_2"], "fragility": [], "watch_items": [], "updated_at": now_iso()})
    o = build_research_overview(tmp_path)  # no repo
    assert o.main_cards[0].reinforcing_factors == ["ev_1", "ev_2"]
