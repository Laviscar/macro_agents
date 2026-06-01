import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.graph_narrative_manager import GraphNarrativeManager
from llm.fake import FakeLLMClient
from repositories.graph_repository import GraphRepository
from schemas.graph_edge import EdgeEvidenceRef, GraphEdge

CONFIG = str(Path(__file__).resolve().parent.parent / "config")
NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _e(label, w, sign=1, dst="GOLD"):
    e = GraphEdge(id=f"{label}->{dst}", src=label, dst=dst, sign=sign, driver_label=label)
    e.weight = w
    return e


# ---- Phase 5: routing ----
def test_route_assets_filters_to_known():
    llm = FakeLLMClient(responses=[json.dumps({"assets": ["GOLD", "外星资产"]})])
    mgr = GraphNarrativeManager(llm_client=llm)
    assert mgr.route_assets("金价创新高", ["GOLD", "NDX", "WTI"]) == ["GOLD"]


def test_route_assets_empty():
    llm = FakeLLMClient(responses=[json.dumps({"assets": []})])
    assert GraphNarrativeManager(llm_client=llm).route_assets("无关新闻", ["GOLD"]) == []


# ---- Task 13: attribution ----
def test_attributes_evidence_to_existing_edge():
    llm = FakeLLMClient(responses=[json.dumps({"driver_label": "央行购金", "aligns_sign": 1})])
    mgr = GraphNarrativeManager(llm_client=llm)
    edges = [_e("实际利率", 0.5, -1), _e("央行购金", 0.2, 1)]
    res = mgr.attribute(evidence_claim="央行连续增持黄金", asset_id="GOLD", incoming_edges=edges)
    assert res is not None and res.edge_driver == "央行购金"


def test_attribution_returns_none_when_driver_not_in_edges():
    llm = FakeLLMClient(responses=[json.dumps({"driver_label": "外星人", "aligns_sign": 1})])
    mgr = GraphNarrativeManager(llm_client=llm)
    res = mgr.attribute("某新闻", "GOLD", [_e("实际利率", 0.5, -1)])
    assert res is None


# ---- Task 14: candidate proposal ----
def test_proposes_candidate_only_when_driver_in_vocab():
    llm = FakeLLMClient(responses=[json.dumps({"src": "AI资本开支", "dst": "VST", "sign": 1, "driver_label": "AI资本开支"})])
    mgr = GraphNarrativeManager(llm_client=llm)
    cand = mgr.propose_edge("数据中心电力需求爆发", "VST", vocab={"AI资本开支"}, existing_edge_ids=set())
    assert cand is not None and cand.driver_label == "AI资本开支" and cand.status == "candidate"


def test_rejects_out_of_vocab_driver():
    llm = FakeLLMClient(responses=[json.dumps({"src": "外星人", "dst": "VST", "sign": 1, "driver_label": "外星人"})])
    mgr = GraphNarrativeManager(llm_client=llm)
    assert mgr.propose_edge("x", "VST", vocab={"AI资本开支"}, existing_edge_ids=set()) is None


def test_rejects_existing_edge():
    llm = FakeLLMClient(responses=[json.dumps({"src": "AI资本开支", "dst": "VST", "sign": 1, "driver_label": "AI资本开支"})])
    mgr = GraphNarrativeManager(llm_client=llm)
    assert mgr.propose_edge("x", "VST", vocab={"AI资本开支"}, existing_edge_ids={"AI资本开支->VST"}) is None


# ---- Task 15: recompute + shift (no LLM) ----
def test_recompute_emits_shift_when_dominant_flips(tmp_path):
    repo = GraphRepository(tmp_path, CONFIG)
    repo.seed_if_empty()
    # GOLD seed: 实际利率 0.6 dominant, 央行购金 0.25. Establish dominant first.
    mgr = GraphNarrativeManager(llm_client=FakeLLMClient())
    mgr.recompute_node(repo, "GOLD", NOW)
    assert repo.get_node("GOLD").dominant_driver == "实际利率"
    # flood 央行购金 edge with fresh evidence so it overtakes
    cb = next(e for e in repo.incoming_edges("GOLD") if e.driver_label == "央行购金")
    for i in range(20):
        cb.supporting_evidence.append(EdgeEvidenceRef(evidence_id=f"ev{i}", created_at=NOW.isoformat(), contribution=0.9))
    repo.save_edge(cb)
    shift = mgr.recompute_node(repo, "GOLD", NOW)
    assert shift is not None and shift.to_driver == "央行购金"
    assert repo.get_node("GOLD").dominant_driver == "央行购金"


# ---- Task 16: narration ----
def test_narrate_sets_fields_and_checks_regime(tmp_path):
    repo = GraphRepository(tmp_path, CONFIG)
    repo.seed_if_empty()
    llm = FakeLLMClient(responses=[json.dumps({
        "title": "黄金:央行购金主导", "thesis": "实际利率影响减弱", "read_line": "金价靠央行买盘撑住",
        "regime": "滞胀", "countries": ["美国", "中国"]})])
    mgr = GraphNarrativeManager(llm_client=llm)
    node = repo.get_node("GOLD")
    mgr.narrate_node(node, repo.incoming_edges("GOLD"), regimes={"滞胀", "软着陆"})
    assert node.title == "黄金:央行购金主导" and node.tags_regime == "滞胀" and node.tags_countries == ["美国", "中国"]


def test_narrate_drops_invalid_regime(tmp_path):
    repo = GraphRepository(tmp_path, CONFIG)
    repo.seed_if_empty()
    llm = FakeLLMClient(responses=[json.dumps({"title": "t", "thesis": "x", "read_line": "y", "regime": "瞎编", "countries": []})])
    mgr = GraphNarrativeManager(llm_client=llm)
    node = repo.get_node("GOLD")
    mgr.narrate_node(node, repo.incoming_edges("GOLD"), regimes={"滞胀"})
    assert node.tags_regime is None


# ---- Task 17: dormancy ----
def test_dormancy_sleeps_quiet_theme_keeps_resident(tmp_path):
    repo = GraphRepository(tmp_path, CONFIG)
    repo.seed_if_empty()
    mgr = GraphNarrativeManager(llm_client=FakeLLMClient())
    # give a theme node (NVDA) stale evidence (40 days old)
    nvda_edge = repo.incoming_edges("NVDA")[0]
    nvda_edge.supporting_evidence.append(EdgeEvidenceRef(
        evidence_id="old", created_at=(NOW - timedelta(days=40)).isoformat(), contribution=0.5))
    repo.save_edge(nvda_edge)
    mgr.apply_dormancy(repo, NOW, dormant_days=21)
    assert repo.get_node("NVDA").status == "dormant"
    assert repo.get_node("GOLD").status == "active"      # resident never sleeps


def test_dormancy_keeps_active_theme_with_fresh_evidence(tmp_path):
    repo = GraphRepository(tmp_path, CONFIG)
    repo.seed_if_empty()
    mgr = GraphNarrativeManager(llm_client=FakeLLMClient())
    e = repo.incoming_edges("NVDA")[0]
    e.supporting_evidence.append(EdgeEvidenceRef(evidence_id="new", created_at=NOW.isoformat(), contribution=0.5))
    repo.save_edge(e)
    mgr.apply_dormancy(repo, NOW, dormant_days=21)
    assert repo.get_node("NVDA").status == "active"


def test_route_assets_none_on_llm_error():
    from llm.base import LLMError
    mgr = GraphNarrativeManager(llm_client=FakeLLMClient(error=LLMError("down")))
    assert mgr.route_assets("x", ["GOLD"]) is None     # None = error, not [] (no-match)


def test_propose_edge_rejects_self_loop():
    mgr = GraphNarrativeManager(llm_client=FakeLLMClient(responses=[
        json.dumps({"src": "MOVE", "dst": "MOVE", "sign": 1, "driver_label": "避险地缘"})]))
    assert mgr.propose_edge("x", "MOVE", vocab={"避险地缘"}, existing_edge_ids=set()) is None
