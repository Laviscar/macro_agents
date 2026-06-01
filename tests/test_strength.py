from datetime import datetime, timedelta, timezone

from graph.strength import compute_edge_weight, compute_node_strength, decayed_contribution
from schemas.graph_edge import EdgeEvidenceRef, GraphEdge

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _ref(days_ago, contrib):
    when = (NOW - timedelta(days=days_ago)).isoformat()
    return EdgeEvidenceRef(evidence_id="e", created_at=when, contribution=contrib)


def _edge(weight, sign, evidence=None):
    e = GraphEdge(id=f"x{weight}->B", src="x", dst="B", sign=sign, driver_label="风险偏好",
                  supporting_evidence=evidence or [])
    e.weight = weight
    return e


# --- decayed_contribution ---
def test_fresh_evidence_full_weight():
    assert decayed_contribution(_ref(0, 0.8), NOW, half_life_days=14) == 0.8


def test_one_half_life_halves():
    assert abs(decayed_contribution(_ref(14, 0.8), NOW, 14) - 0.4) < 1e-9


def test_two_half_lives_quarter():
    assert abs(decayed_contribution(_ref(28, 0.8), NOW, 14) - 0.2) < 1e-9


# --- compute_edge_weight ---
def test_empty_edge_weight_zero():
    assert compute_edge_weight(_edge(0.0, 1), NOW) == 0.0


def test_more_fresh_evidence_higher_but_bounded():
    e2 = _edge(0.0, 1, [_ref(0, 0.5), _ref(0, 0.5)])
    e1 = _edge(0.0, 1, [_ref(0, 0.5)])
    w2, w1 = compute_edge_weight(e2, NOW), compute_edge_weight(e1, NOW)
    assert 0.0 < w1 < w2 < 1.0


def test_old_evidence_contributes_less():
    fresh = compute_edge_weight(_edge(0.0, 1, [_ref(0, 0.6)]), NOW)
    stale = compute_edge_weight(_edge(0.0, 1, [_ref(28, 0.6)]), NOW)
    assert stale < fresh


# --- compute_node_strength ---
def test_no_edges_neutral():
    assert compute_node_strength([]) == (0.5, 0.5)


def test_net_positive_above_half():
    s, _ = compute_node_strength([_edge(0.8, 1), _edge(0.2, -1)])
    assert s > 0.5


def test_net_negative_below_half():
    s, _ = compute_node_strength([_edge(0.2, 1), _edge(0.8, -1)])
    assert s < 0.5


def test_balanced_near_half():
    s, _ = compute_node_strength([_edge(0.5, 1), _edge(0.5, -1)])
    assert abs(s - 0.5) < 1e-9
