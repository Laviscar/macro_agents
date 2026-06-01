from datetime import datetime, timezone
from pathlib import Path

from presenters.today_presenter import build_allocation_overview, build_shifts_view, build_today_view
from repositories.graph_repository import GraphRepository
from schemas.graph_edge import EdgeEvidenceRef

CONFIG = str(Path(__file__).resolve().parent.parent / "config")
NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _repo(tmp_path):
    r = GraphRepository(tmp_path, CONFIG)
    r.seed_if_empty()
    return r


def _add_evidence(repo, asset, driver, n, contrib=0.5):
    e = next(x for x in repo.incoming_edges(asset) if x.driver_label == driver)
    for i in range(n):
        e.supporting_evidence.append(EdgeEvidenceRef(evidence_id=f"{asset}{driver}{i}", created_at=NOW.isoformat(), contribution=contrib))
    repo.save_edge(e)


def test_today_ranks_shifting_first(tmp_path):
    repo = _repo(tmp_path)
    # mark GOLD as shifting via a stored shift
    from graph.driver_shift import DriverShift
    repo.save_driver_shift(DriverShift(node_id="GOLD", from_driver="实际利率", to_driver="央行购金", at=NOW.isoformat()))
    view = build_today_view(repo, top_n=5)
    assert view.available
    assert view.cards[0].asset_id == "GOLD" and view.cards[0].is_shifting


def test_today_evidence_volume_ranks_up(tmp_path):
    repo = _repo(tmp_path)
    _add_evidence(repo, "COPPER", "制造业周期", 8)
    view = build_today_view(repo, top_n=3)
    assert "COPPER" in {c.asset_id for c in view.cards}


def test_today_pinned_forced_top(tmp_path):
    repo = _repo(tmp_path)
    view = build_today_view(repo, top_n=5, pinned=["WTI"])
    assert view.cards[0].asset_id == "WTI"


def test_shifts_view_lists_shift_and_contested(tmp_path):
    repo = _repo(tmp_path)
    from graph.driver_shift import DriverShift
    repo.save_driver_shift(DriverShift(node_id="GOLD", from_driver="实际利率", to_driver="央行购金", at=NOW.isoformat()))
    view = build_shifts_view(repo)
    assert view.available
    assert any(s.node_id == "GOLD" and s.to_driver == "央行购金" for s in view.shifts)


def test_stance_lean_from_strength(tmp_path):
    repo = _repo(tmp_path)
    g = repo.get_node("GOLD"); g.strength = 0.7; repo.save_node(g)
    card = next(c for c in build_today_view(repo, top_n=41, pinned=["GOLD"]).cards if c.asset_id == "GOLD")
    assert card.lean == "偏多"


def test_contested_reversal_vs_same_sign(tmp_path):
    from schemas.graph_edge import EdgeEvidenceRef
    repo = _repo(tmp_path)
    # GOLD: 实际利率(-) vs 央行购金(+) are opposite signs -> reversal risk when contested
    for drv in ("实际利率", "央行购金"):
        e = next(x for x in repo.incoming_edges("GOLD") if x.driver_label == drv)
        e.supporting_evidence = [EdgeEvidenceRef(evidence_id=f"{drv}1", created_at=NOW.isoformat(), contribution=0.5)]
        e.weight = 0.5  # tie -> contested
        repo.save_edge(e)
    view = build_shifts_view(repo)
    gold = next((c for c in view.contested if c.node_id == "GOLD"), None)
    assert gold is not None and gold.is_reversal is True


def test_allocation_overview_clusters_by_regime(tmp_path):
    repo = _repo(tmp_path)
    g = repo.get_node("GOLD"); g.tags_regime = "risk-off"; g.strength = 0.7; repo.save_node(g)
    n = repo.get_node("NDX"); n.tags_regime = "risk-on"; n.strength = 0.7; repo.save_node(n)
    a = build_allocation_overview(repo)
    assert a.available
    regimes = {c.regime for c in a.clusters}
    assert {"risk-off", "risk-on"} <= regimes
