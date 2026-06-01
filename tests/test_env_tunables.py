from datetime import datetime, timedelta, timezone

from graph.driver_shift import contested, dominant_edge
from graph.strength import compute_edge_weight
from schemas.graph_edge import EdgeEvidenceRef, GraphEdge

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _edge(weight, evidence=None):
    e = GraphEdge(id="x->B", src="x", dst="B", sign=1, driver_label="风险偏好", supporting_evidence=evidence or [])
    e.weight = weight
    return e


def test_half_life_env_honored(monkeypatch):
    ref = EdgeEvidenceRef(evidence_id="e", created_at=(NOW - timedelta(days=14)).isoformat(), contribution=0.8)
    e = _edge(0.0, [ref])
    # default 14d half-life: 14-day-old evidence is halved
    base = compute_edge_weight(e, NOW)
    monkeypatch.setenv("NARRATIVE_HALF_LIFE_DAYS", "7")   # shorter half-life => more decay => lower weight
    faster = compute_edge_weight(e, NOW)
    assert faster < base


def test_min_dominant_weight_env(monkeypatch):
    edges = [_edge(0.2)]
    assert dominant_edge(edges) is not None             # 0.2 >= default 0.15
    monkeypatch.setenv("DRIVER_MIN_DOMINANT_WEIGHT", "0.3")
    assert dominant_edge(edges) is None                 # 0.2 < 0.3


def test_contested_gap_env(monkeypatch):
    edges = [_edge(0.50), _edge(0.42)]                   # gap 0.08
    assert contested(edges) is True                     # < default 0.10
    monkeypatch.setenv("DRIVER_CONTESTED_GAP", "0.05")
    assert contested(edges) is False                    # 0.08 not < 0.05
