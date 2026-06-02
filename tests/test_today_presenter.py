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


def test_same_sign_switch_shows_quality_verdict(tmp_path):
    from schemas.graph_edge import EdgeEvidenceRef
    repo = _repo(tmp_path)
    # SMH: AI资本开支(结构性,+) vs 风险偏好(情绪事件,+) — same sign, structural->sentiment = quality down
    for drv in ("AI资本开支", "风险偏好"):
        e = next(x for x in repo.incoming_edges("SMH") if x.driver_label == drv)
        e.supporting_evidence = [EdgeEvidenceRef(evidence_id=f"{drv}1", created_at=NOW.isoformat(), contribution=0.5)]
        e.weight = 0.5
        repo.save_edge(e)
    c = next(x for x in build_shifts_view(repo).contested if x.node_id == "SMH")
    assert c.is_reversal is False
    assert "支撑质量" in c.implication and ("结构性" in c.implication or "情绪事件" in c.implication)


def test_factor_nature_loaded(tmp_path):
    repo = _repo(tmp_path)
    nat = repo.factor_nature()
    assert nat.get("AI资本开支") == "结构性" and nat.get("风险偏好") == "情绪事件"


def test_shifts_view_carries_lean_and_direction(tmp_path):
    from schemas.graph_edge import EdgeEvidenceRef
    repo = _repo(tmp_path)
    # make GOLD net-long and contested between 实际利率(-) and 央行购金(+)
    for drv, w in (("实际利率", 0.45), ("央行购金", 0.5)):
        e = next(x for x in repo.incoming_edges("GOLD") if x.driver_label == drv)
        e.supporting_evidence = [EdgeEvidenceRef(evidence_id=f"{drv}", created_at=NOW.isoformat(), contribution=0.6)]
        e.weight = w
        repo.save_edge(e)
    g = repo.get_node("GOLD"); g.strength = 0.7; repo.save_node(g)
    c = next(x for x in build_shifts_view(repo).contested if x.node_id == "GOLD")
    assert c.current_lean == "偏多"
    assert {c.from_dir, c.to_dir} == {"利多", "利空"}   # opposite-sign drivers
    assert c.is_reversal is True


def test_today_card_carries_committee_badge(tmp_path):
    from repositories.committee_repository import CommitteeRepository
    from schemas.committee import CommitteeSession, CommitteeSeat, CommitteeVerdict, SeatRemark
    repo = _repo(tmp_path)
    cr = CommitteeRepository(tmp_path, CONFIG)
    v = CommitteeVerdict(bottom_line="b", whats_changing="w", switch_likelihood="将至", direction="偏空",
        conviction="高", confidence=0.8, time_horizon="t", catalysts_to_watch=[], invalidation="i",
        positioning="p", key_disagreements=[], evidence_basis=[])
    cr.save_session(CommitteeSession(id="GOLD_t", asset_id="GOLD", asset_name="黄金", level=0.75,
        seats=[CommitteeSeat(name="A", persona="鹰派")], rounds=1, mode="cross",
        remarks=[SeatRemark(seat_name="A", persona="鹰派", round=1, critique="c")], verdict=v, created_at="t"))
    view = build_today_view(repo, committee_repo=cr, pinned=["GOLD"])
    card = next(c for c in view.cards if c.asset_id == "GOLD")
    assert card.committee_badge == "将至·偏空·信心高"
