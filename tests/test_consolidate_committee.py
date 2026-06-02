import json
from pathlib import Path

from agents.graph_narrative_manager import GraphNarrativeManager
from llm.fake import FakeLLMClient
from pipelines.stages import consolidate_graph
from repositories.committee_repository import CommitteeRepository
from repositories.graph_repository import GraphRepository
from repositories.news_repository import SQLiteNewsRepository
from tests.test_consolidate_graph import CONFIG, REGIMES, VOCAB, _seed_evidence
from utils.clock import now_iso


def test_consolidate_emits_committee_pending(tmp_path):
    news = SQLiteNewsRepository(tmp_path / "n.sqlite3")
    graph = GraphRepository(tmp_path, CONFIG)
    graph.seed_if_empty()
    committee = CommitteeRepository(tmp_path, CONFIG)
    llm = FakeLLMClient(responses=[
        json.dumps({"assets": ["GOLD"]}),
        json.dumps({"driver_label": "央行购金", "aligns_sign": 1}),
        json.dumps({"title": "g", "thesis": "t", "read_line": "r", "regime": "滞胀", "countries": []}),
    ])
    mgr = GraphNarrativeManager(llm_client=llm)
    _seed_evidence(news, "央行增持黄金", "ev1")
    out = consolidate_graph(news, graph, mgr, VOCAB, REGIMES, tmp_path / "rs.json", now_fn=now_iso,
                            committee_repo=committee, trigger_levels=[0.60, 0.75, 0.90], velocity_delta=0.10)
    # integration wired without crashing; pending is a list and trigger state persisted
    assert "committee_pending" in out
    assert isinstance(committee.list_pending(), list)
    assert isinstance(committee.load_trigger_state(), dict)


def test_committee_evaluates_even_with_no_new_evidence(tmp_path):
    """The bug fix: committee trigger must run even when there's nothing new to consolidate."""
    from datetime import datetime, timezone
    from schemas.graph_edge import EdgeEvidenceRef
    news = SQLiteNewsRepository(tmp_path / "n.sqlite3")
    graph = GraphRepository(tmp_path, CONFIG); graph.seed_if_empty()
    committee = CommitteeRepository(tmp_path, CONFIG)
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    # craft a contested GOLD directly in the graph (no news evidence pipeline)
    for drv, w, wp in (("实际利率", 0.50, 0.50), ("央行购金", 0.46, 0.30)):
        e = next(x for x in graph.incoming_edges("GOLD") if x.driver_label == drv)
        e.weight, e.weight_prev = w, wp
        e.supporting_evidence = [EdgeEvidenceRef(evidence_id=drv, created_at=now.isoformat(), contribution=0.5)]
        graph.save_edge(e)
    from agents.graph_narrative_manager import GraphNarrativeManager
    out = consolidate_graph(news, graph, GraphNarrativeManager(llm_client=FakeLLMClient()),
                            VOCAB, REGIMES, tmp_path / "rs.json", now_fn=now_iso,
                            committee_repo=committee, trigger_levels=[0.60, 0.75, 0.90], velocity_delta=0.10)
    assert out["consolidated_evidence"] == 0           # no news evidence
    assert out["committee_pending"] > 0                # but committee still flagged GOLD
    assert any(p.asset_id == "GOLD" for p in committee.list_pending())
