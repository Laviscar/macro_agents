import json
from pathlib import Path

from agents.graph_narrative_manager import GraphNarrativeManager
from llm.fake import FakeLLMClient
from pipelines.stages import consolidate_graph
from repositories.graph_repository import GraphRepository
from repositories.news_repository import SQLiteNewsRepository
from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence
from schemas.raw_news_item import RawNewsItem
from utils.clock import now_iso

CONFIG = str(Path(__file__).resolve().parent.parent / "config")
VOCAB = {"实际利率", "央行购金", "避险地缘", "风险偏好", "AI资本开支"}
REGIMES = {"再通胀", "软着陆", "衰退", "滞胀", "risk-on", "risk-off"}


def _seed_evidence(repo: SQLiteNewsRepository, claim: str, ev_id: str):
    nid = repo.insert_news_item(RawNewsItem(source_type="rss", source_name="s", external_id=ev_id,
        url=f"https://x/{ev_id}", title="t", summary="s", published_at=now_iso(),
        fetched_at=now_iso(), raw_payload={}))
    card = AnalysisCard(id=f"ac_{ev_id}", event_id="e", source_card_ids=["e"], reframed_question="q",
        signal_level="structure", thesis="t", evidence_for=["x"], evidence_against=[], macro_variables=["m"],
        asset_mapping=[], confidence=0.8, mainline_relation="supports", candidate_branch_title=None,
        invalidation_conditions=[], created_at=now_iso())
    ev = Evidence(id=ev_id, source_analysis_id=f"ac_{ev_id}", source_card_ids=["e"], claim=claim,
        relation_type="supports", target_main_narrative_id="main_default", target_branch_id=None,
        strength=0.9, confidence=0.9, why="w", counter_evidence=[], created_at=now_iso())
    repo.save_analysis_bundle(nid, card, [ev])


def test_consolidate_routes_attributes_and_recomputes(tmp_path):
    news = SQLiteNewsRepository(tmp_path / "n.sqlite3")
    graph = GraphRepository(tmp_path, CONFIG)
    graph.seed_if_empty()
    # LLM: route GOLD -> attribute 央行购金. One evidence.
    llm = FakeLLMClient(responses=[
        json.dumps({"assets": ["GOLD"]}),                       # route_assets
        json.dumps({"driver_label": "央行购金", "aligns_sign": 1}),  # attribute
        json.dumps({"title": "黄金", "thesis": "t", "read_line": "r", "regime": "滞胀", "countries": ["中国"]}),  # narrate
    ])
    mgr = GraphNarrativeManager(llm_client=llm)
    _seed_evidence(news, "央行连续增持黄金", "ev1")
    run_state = tmp_path / "run_state.json"

    out = consolidate_graph(news, graph, mgr, VOCAB, REGIMES, run_state, now_fn=now_iso)

    assert out["consolidated_evidence"] == 1 and out["touched"] == 1
    # evidence landed on GOLD's 央行购金 edge
    cb = next(e for e in graph.incoming_edges("GOLD") if e.driver_label == "央行购金")
    assert any(r.evidence_id == "ev1" for r in cb.supporting_evidence)
    # GOLD node updated + narrated
    gold = graph.get_node("GOLD")
    assert gold.dominant_driver is not None and gold.title == "黄金" and gold.tags_regime == "滞胀"
    # watermark advanced -> a second run with no new evidence is a no-op
    out2 = consolidate_graph(news, graph, mgr, VOCAB, REGIMES, run_state, now_fn=now_iso)
    assert out2["consolidated_evidence"] == 0


def test_consolidate_proposes_candidate_when_no_edge_matches(tmp_path):
    news = SQLiteNewsRepository(tmp_path / "n.sqlite3")
    graph = GraphRepository(tmp_path, CONFIG)
    graph.seed_if_empty()
    # URA has no incoming seed edges -> attribute short-circuits (no LLM call) -> propose
    llm = FakeLLMClient(responses=[
        json.dumps({"assets": ["URA"]}),                                            # route
        json.dumps({"src": "AI资本开支", "dst": "URA", "sign": 1, "driver_label": "AI资本开支"}),  # propose
        json.dumps({"title": "铀", "thesis": "t", "read_line": "r", "regime": None, "countries": []}),  # narrate
    ])
    mgr = GraphNarrativeManager(llm_client=llm)
    _seed_evidence(news, "AI数据中心推动核电与铀需求", "ev2")
    out = consolidate_graph(news, graph, mgr, VOCAB, REGIMES, tmp_path / "rs.json", now_fn=now_iso)
    assert out["consolidated_evidence"] == 1
    cands = graph.list_candidates()
    assert any(c.dst == "URA" and c.driver_label == "AI资本开支" for c in cands)
