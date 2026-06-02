from schemas.graph_edge import EdgeEvidenceRef, GraphEdge


def test_edge_defaults():
    e = GraphEdge(id="实际利率->GOLD", src="实际利率", dst="GOLD", sign=-1, driver_label="实际利率")
    assert e.weight == 0.0 and e.status == "active" and e.supporting_evidence == []


def test_evidence_ref():
    r = EdgeEvidenceRef(evidence_id="ev1", created_at="2026-06-01T00:00:00Z", contribution=0.3)
    assert r.contribution == 0.3


def test_roundtrip_with_evidence():
    e = GraphEdge(id="央行购金->GOLD", src="央行购金", dst="GOLD", sign=1, driver_label="央行购金",
                  weight=0.4, supporting_evidence=[
                      EdgeEvidenceRef(evidence_id="ev1", created_at="2026-06-01T00:00:00Z", contribution=0.3)])
    again = GraphEdge.model_validate_json(e.model_dump_json())
    assert again.weight == 0.4 and again.supporting_evidence[0].evidence_id == "ev1"


def test_edge_has_weight_prev_default_zero():
    from schemas.graph_edge import GraphEdge
    e = GraphEdge(id="a->B", src="a", dst="B", sign=1, driver_label="风险偏好")
    assert e.weight_prev == 0.0
