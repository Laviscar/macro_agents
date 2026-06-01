from pathlib import Path

from repositories.graph_repository import GraphRepository
from schemas.graph_edge import EdgeEvidenceRef, GraphEdge

CONFIG = str(Path(__file__).resolve().parent.parent / "config")


def _repo(tmp_path):
    return GraphRepository(storage_root=tmp_path, config_dir=CONFIG)


# ---- seeding ----
def test_seed_creates_nodes_and_edges(tmp_path):
    repo = _repo(tmp_path)
    repo.seed_if_empty()
    nodes = repo.list_nodes()
    assert any(n.id == "GOLD" and n.kind == "asset" for n in nodes)
    assert any(n.id == "实际利率" and n.kind == "factor" for n in nodes)
    gold_in = repo.incoming_edges("GOLD")
    assert {e.driver_label for e in gold_in} >= {"实际利率", "央行购金"}


def test_seed_idempotent(tmp_path):
    repo = _repo(tmp_path)
    repo.seed_if_empty()
    n1 = len(repo.list_nodes())
    repo.seed_if_empty()
    assert len(repo.list_nodes()) == n1


def test_seed_init_weights_loaded(tmp_path):
    repo = _repo(tmp_path)
    repo.seed_if_empty()
    real_rate_gold = next(e for e in repo.incoming_edges("GOLD") if e.driver_label == "实际利率")
    assert real_rate_gold.weight == 0.6  # from transmission_seed.yaml


# ---- CRUD / queries ----
def test_incoming_edges_active_only(tmp_path):
    repo = _repo(tmp_path)
    repo.seed_if_empty()
    edges = repo.incoming_edges("GOLD")
    assert edges and all(e.dst == "GOLD" and e.status == "active" for e in edges)


def test_assets_with_new_evidence(tmp_path):
    repo = _repo(tmp_path)
    repo.seed_if_empty()
    e = repo.incoming_edges("GOLD")[0]
    e.supporting_evidence.append(EdgeEvidenceRef(
        evidence_id="x", created_at="2026-06-01T12:00:00Z", contribution=0.3))
    repo.save_edge(e)
    assert "GOLD" in repo.assets_with_new_evidence(since="2026-06-01T00:00:00Z")
    assert "GOLD" not in repo.assets_with_new_evidence(since="2026-06-02T00:00:00Z")


def test_edge_id_with_slash_roundtrips(tmp_path):
    repo = _repo(tmp_path)
    e = GraphEdge(id="ETH/BTC->BTC", src="ETH/BTC", dst="BTC", sign=1, driver_label="风险偏好")
    repo.save_edge(e)
    assert repo.get_edge("ETH/BTC->BTC") is not None


# ---- candidates ----
def test_candidate_promote(tmp_path):
    repo = _repo(tmp_path)
    repo.seed_if_empty()
    cand = GraphEdge(id="AI资本开支->URA", src="AI资本开支", dst="URA", sign=1, driver_label="AI资本开支")
    repo.add_candidate_edge(cand)
    assert len(repo.list_candidates()) == 1
    promoted = repo.promote_candidate("AI资本开支->URA")
    assert promoted.status == "active"
    assert repo.get_edge("AI资本开支->URA") is not None
    assert repo.list_candidates() == []


def test_candidate_reject(tmp_path):
    repo = _repo(tmp_path)
    cand = GraphEdge(id="外星人->URA", src="外星人", dst="URA", sign=1, driver_label="AI资本开支")
    repo.add_candidate_edge(cand)
    repo.reject_candidate("外星人->URA")
    assert repo.list_candidates() == []
    assert repo.get_edge("外星人->URA") is None
