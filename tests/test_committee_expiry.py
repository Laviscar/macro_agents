from pathlib import Path

from repositories.committee_repository import CommitteeRepository
from schemas.committee import PendingConvocation

CONFIG = str(Path(__file__).resolve().parent.parent / "config")


def _p(asset, ct, trigger="proximity", level=0.6):
    return PendingConvocation(asset_id=asset, asset_name=asset, trigger=trigger, level=level,
                              ratio=0.7, leader="实际利率", runner_up="央行购金", is_reversal=True, created_at=ct)


def test_supersede_expires_older_same_asset_keeps_newer_and_others(tmp_path):
    repo = CommitteeRepository(tmp_path, CONFIG)
    repo.save_pending(_p("GOLD", "2026-06-01T00:00:00Z"))
    repo.save_pending(_p("WTI", "2026-06-01T00:00:00Z"))
    n = repo.supersede_pending("GOLD", "2026-06-08T00:00:00Z")
    assert n == 1
    by = {p.asset_id: p.status for p in repo.list_pending()}
    assert by["GOLD"] == "expired" and by["WTI"] == "active"     # only same asset, only older
    repo.save_pending(_p("GOLD", "2026-06-08T00:00:00Z", level=0.75))
    actives = [p for p in repo.list_active_pending() if p.asset_id == "GOLD"]
    assert len(actives) == 1 and actives[0].level == 0.75       # new one active, old expired kept


def test_supersede_keeps_same_timestamp_batch_active(tmp_path):
    repo = CommitteeRepository(tmp_path, CONFIG)
    repo.save_pending(_p("GOLD", "2026-06-08T00:00:00Z", trigger="proximity", level=0.6))
    repo.save_pending(_p("GOLD", "2026-06-08T00:00:00Z", trigger="velocity", level=None))
    repo.supersede_pending("GOLD", "2026-06-08T00:00:00Z")      # same ct -> not < keep -> stay active
    assert len(repo.list_active_pending()) == 2
