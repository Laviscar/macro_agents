import json

from presenters.briefing_presenter import build_briefing_overview


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_empty_storage_returns_unavailable(tmp_path):
    overview = build_briefing_overview(tmp_path)
    assert overview.available is False


def _seed(tmp_path):
    _write(tmp_path / "main_narrative_state" / "main_default.json", {
        "id": "main_default", "title": "美国反通胀", "status": "active",
        "strength": 0.62, "confidence": 0.58, "read_line": "反通胀延续,能源是变数。",
        "updated_at": "2026-05-30T18:10:00Z",
    })
    _write(tmp_path / "narrative_commits" / "c1.json", {
        "id": "c1", "narrative_type": "main", "summary": "CPI 降温强化主线",
        "field_changes": {"strength": {"from": 0.50, "to": 0.58}, "confidence": {"from": 0.50, "to": 0.56}},
        "created_at": "2026-05-30T17:00:00Z",
    })
    _write(tmp_path / "narrative_commits" / "c2.json", {
        "id": "c2", "narrative_type": "main", "summary": "地缘风险削弱主线",
        "field_changes": {"strength": {"from": 0.58, "to": 0.62}, "confidence": {"from": 0.56, "to": 0.58}},
        "created_at": "2026-05-30T18:10:00Z",
    })
    _write(tmp_path / "branch_narrative_state" / "b1.json", {
        "id": "b1", "title": "伊朗机会窗口", "challenge_probability": 0.75, "key_triggers": ["制裁松动"],
    })
    _write(tmp_path / "branch_narrative_state" / "b2.json", {
        "id": "b2", "title": "低概率分支", "challenge_probability": 0.40, "key_triggers": [],
    })


def test_briefing_core_fields(tmp_path):
    _seed(tmp_path)
    o = build_briefing_overview(tmp_path)
    assert o.available is True
    assert o.title == "美国反通胀"
    assert o.read_line == "反通胀延续,能源是变数。"
    assert o.strength == 0.62
    # latest commit strength delta = 0.62 - 0.58 = 0.04
    assert round(o.strength_delta, 2) == 0.04


def test_briefing_strength_series_from_commits(tmp_path):
    _seed(tmp_path)
    o = build_briefing_overview(tmp_path)
    # seeded with first commit's 'from' (0.50), then each 'to': 0.58, 0.62
    assert o.strength_series == [0.50, 0.58, 0.62]


def test_briefing_recent_changes_newest_first_with_direction(tmp_path):
    _seed(tmp_path)
    o = build_briefing_overview(tmp_path)
    assert len(o.recent_changes) == 2
    assert o.recent_changes[0].summary == "地缘风险削弱主线"  # newest first
    assert o.recent_changes[0].direction == "强化"  # 0.58->0.62 is +


def test_briefing_top_branches_sorted_and_capped(tmp_path):
    _seed(tmp_path)
    o = build_briefing_overview(tmp_path)
    assert len(o.top_branches) == 2
    assert o.top_branches[0].title == "伊朗机会窗口"
    assert o.top_branches[0].challenge_probability == 0.75
