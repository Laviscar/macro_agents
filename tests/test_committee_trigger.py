from datetime import datetime, timezone
from pathlib import Path

from committee.trigger import crossed_levels, evaluate_assets, velocity_fired
from repositories.graph_repository import GraphRepository
from schemas.graph_edge import EdgeEvidenceRef

CONFIG = str(Path(__file__).resolve().parent.parent / "config")
NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)
LEVELS = [0.60, 0.75, 0.90]


# --- crossed_levels ---
def test_crosses_one_band_first_time():
    new, highest = crossed_levels(0.62, 0.0, LEVELS)
    assert new == [0.60] and highest == 0.60


def test_jump_crosses_multiple_bands():
    new, highest = crossed_levels(0.91, 0.0, LEVELS)
    assert new == [0.60, 0.75, 0.90] and highest == 0.90


def test_no_refire_within_same_band():
    new, highest = crossed_levels(0.80, 0.75, LEVELS)
    assert new == [] and highest == 0.75


# --- velocity_fired ---
def test_velocity_fires_when_delta_exceeds_and_not_already():
    assert velocity_fired(0.15, 0.10, False) is True


def test_velocity_no_refire_when_already_fired():
    assert velocity_fired(0.15, 0.10, True) is False


# --- evaluate_assets ---
def _contested_gold(tmp_path):
    repo = GraphRepository(tmp_path, CONFIG)
    repo.seed_if_empty()
    for drv, w, wp in (("实际利率", 0.50, 0.50), ("央行购金", 0.46, 0.30)):
        e = next(x for x in repo.incoming_edges("GOLD") if x.driver_label == drv)
        e.weight, e.weight_prev = w, wp
        e.supporting_evidence = [EdgeEvidenceRef(evidence_id=drv, created_at=NOW.isoformat(), contribution=0.5)]
        repo.save_edge(e)
    return repo


def test_proximity_pending_created(tmp_path):
    repo = _contested_gold(tmp_path)              # ratio 0.46/0.50 = 0.92 -> 0.60/0.75/0.90
    pendings = evaluate_assets(repo, {}, LEVELS, 0.10)
    gold = [p for p in pendings if p.asset_id == "GOLD" and p.trigger == "proximity"]
    assert gold and gold[0].leader == "实际利率" and gold[0].runner_up == "央行购金"


def test_velocity_pending_created(tmp_path):
    repo = _contested_gold(tmp_path)              # 央行购金 delta = 0.46-0.30 = 0.16 >= 0.10
    pendings = evaluate_assets(repo, {}, LEVELS, 0.10)
    assert any(p.asset_id == "GOLD" and p.trigger == "velocity" for p in pendings)


def test_state_debounces_second_call(tmp_path):
    repo = _contested_gold(tmp_path)
    state = {}
    evaluate_assets(repo, state, LEVELS, 0.10)
    assert evaluate_assets(repo, state, LEVELS, 0.10) == []   # nothing new on identical graph


def test_reversal_only_filters_same_sign(tmp_path):
    repo = GraphRepository(tmp_path, CONFIG); repo.seed_if_empty()
    # SPX contested by two SAME-sign (+) drivers -> should NOT trigger under reversal_only
    for drv, w, wp in (("风险偏好", 0.50, 0.50), ("增长预期", 0.46, 0.30)):
        e = next((x for x in repo.incoming_edges("SPX") if x.driver_label == drv), None)
        if e is None:
            continue
        e.weight, e.weight_prev = w, wp
        e.supporting_evidence = [EdgeEvidenceRef(evidence_id=drv, created_at=NOW.isoformat(), contribution=0.5)]
        repo.save_edge(e)
    assert evaluate_assets(repo, {}, LEVELS, 0.10, reversal_only=True) == []          # same-sign filtered
    # GOLD with opposite-sign drivers still triggers
    for drv, w, wp in (("实际利率", 0.50, 0.50), ("央行购金", 0.46, 0.30)):
        e = next(x for x in repo.incoming_edges("GOLD") if x.driver_label == drv)
        e.weight, e.weight_prev = w, wp
        e.supporting_evidence = [EdgeEvidenceRef(evidence_id=drv, created_at=NOW.isoformat(), contribution=0.5)]
        repo.save_edge(e)
    assert any(p.asset_id == "GOLD" for p in evaluate_assets(repo, {}, LEVELS, 0.10, reversal_only=True))
