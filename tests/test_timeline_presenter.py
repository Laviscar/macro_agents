import json

from presenters.timeline_presenter import build_narrative_timeline


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_empty_returns_unavailable(tmp_path):
    assert build_narrative_timeline(tmp_path).available is False


def _seed(tmp_path):
    _write(tmp_path / "main_narrative_state" / "main_default.json", {
        "id": "main_default", "title": "美国反通胀", "status": "active",
        "strength": 0.62, "confidence": 0.58, "updated_at": "2026-05-30T18:10:00Z",
    })
    _write(tmp_path / "narrative_commits" / "c1.json", {
        "id": "c1", "narrative_type": "main", "summary": "CPI 降温强化主线",
        "field_changes": {"strength": {"from": 0.50, "to": 0.58}, "confidence": {"from": 0.50, "to": 0.56}},
        "source_evidence_ids": ["ev1"], "created_at": "2026-05-30T17:00:00Z",
    })
    _write(tmp_path / "narrative_commits" / "c2.json", {
        "id": "c2", "narrative_type": "branch", "summary": "出现挑战分支",
        "field_changes": {"branch_strength": {"from": 0.0, "to": 0.6}, "challenge_probability": {"from": 0.0, "to": 0.7}},
        "source_evidence_ids": ["ev2", "ev3"], "created_at": "2026-05-30T18:10:00Z",
    })


def test_timeline_basic_fields(tmp_path):
    _seed(tmp_path)
    t = build_narrative_timeline(tmp_path)
    assert t.available is True
    assert t.title == "美国反通胀"
    assert t.total_commits == 2


def test_series_seeded_and_carried_forward(tmp_path):
    _seed(tmp_path)
    t = build_narrative_timeline(tmp_path)
    # seed(0.50) + c1 -> 0.58 + c2 (no strength change -> carry 0.58)
    assert t.strength_series == [0.50, 0.58, 0.58]
    assert t.confidence_series == [0.50, 0.56, 0.56]
    assert len(t.series_labels) == 3


def test_points_newest_first_with_direction_and_evidence_count(tmp_path):
    _seed(tmp_path)
    t = build_narrative_timeline(tmp_path)
    assert t.points[0].summary == "出现挑战分支"      # newest first
    assert t.points[0].direction == "挑战"             # branch commit, no strength change
    assert t.points[0].evidence_count == 2
    assert t.points[1].direction == "强化"             # 0.50 -> 0.58
    assert t.points[1].evidence_count == 1


def test_window_days_excludes_old_commits(tmp_path):
    _seed(tmp_path)
    # add a stale commit ~1 year old; default 30d window must drop it
    _write(tmp_path / "narrative_commits" / "c0_old.json", {
        "id": "c0", "narrative_type": "main", "summary": "去年的旧提交",
        "field_changes": {"strength": {"from": 0.40, "to": 0.50}},
        "source_evidence_ids": [], "created_at": "2025-05-30T00:00:00Z",
    })
    assert build_narrative_timeline(tmp_path, window_days=30).total_commits == 2  # old one excluded
    assert build_narrative_timeline(tmp_path, window_days=None).total_commits == 3  # all kept


def test_key_only_filters_neutral_main_commits(tmp_path):
    _seed(tmp_path)
    # a no-change neutral main commit (strength unchanged) is noise
    _write(tmp_path / "narrative_commits" / "c3_neutral.json", {
        "id": "c3", "narrative_type": "main", "summary": "无变化的中性提交",
        "field_changes": {}, "source_evidence_ids": [], "created_at": "2026-05-30T19:00:00Z",
    })
    key = build_narrative_timeline(tmp_path, key_only=True)
    assert key.total_commits == 3                       # window count unchanged
    assert key.key_count == 2                            # neutral dropped
    assert all(p.summary != "无变化的中性提交" for p in key.points)
    full = build_narrative_timeline(tmp_path, key_only=False)
    assert full.key_count == 3 and len(full.points) == 3
