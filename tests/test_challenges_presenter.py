import json

from presenters.challenges_presenter import build_challenges_overview


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_empty_returns_unavailable(tmp_path):
    assert build_challenges_overview(tmp_path).available is False


def _seed(tmp_path):
    _write(tmp_path / "branch_narrative_state" / "b1.json", {
        "id": "b1", "title": "伊朗机会窗口", "status": "challenger",
        "challenge_probability": 0.75, "branch_strength": 0.6,
        "core_claims": ["制裁失效"], "key_triggers": ["制裁松动"], "supporting_evidence": ["ev1", "ev2"],
    })
    _write(tmp_path / "branch_narrative_state" / "b2.json", {
        "id": "b2", "title": "低概率分支", "status": "seed",
        "challenge_probability": 0.40, "branch_strength": 0.2,
        "core_claims": [], "key_triggers": [], "supporting_evidence": [],
    })
    _write(tmp_path / "alerts" / "a1.json", {
        "id": "a1", "main_narrative_id": "main_default", "branch_narrative_id": "b1",
        "challenged_claim": "主线被伊朗变量挑战", "challenge_probability": 0.75, "key_triggers": ["制裁松动"],
        "created_at": "2026-05-30T18:00:00Z",
    })
    _write(tmp_path / "alerts" / "_status.json", {"status": "no_alert", "message": "x"})  # sentinel, must be ignored
    _write(tmp_path / "scenarios" / "s1.json", {
        "id": "s1", "main_narrative_id": "main_default", "branch_narrative_id": "b1",
        "scenario_a_name": "主线延续", "scenario_b_name": "分支上位",
        "probability_split": {"scenario_a": 0.25, "scenario_b": 0.75},
    })


def test_alerts_skip_sentinel_and_carry_branch_title(tmp_path):
    _seed(tmp_path)
    o = build_challenges_overview(tmp_path)
    assert len(o.alerts) == 1  # _status.json ignored
    assert o.alerts[0].branch_title == "伊朗机会窗口"
    assert o.alerts[0].challenge_probability == 0.75


def test_challenges_sorted_by_probability_with_scenario(tmp_path):
    _seed(tmp_path)
    o = build_challenges_overview(tmp_path)
    assert [c.title for c in o.challenges] == ["伊朗机会窗口", "低概率分支"]
    top = o.challenges[0]
    assert top.supporting_evidence_count == 2
    assert top.scenario is not None
    assert top.scenario.scenario_b_prob == 0.75


def test_headline_counts(tmp_path):
    _seed(tmp_path)
    o = build_challenges_overview(tmp_path)
    assert "2 条挑战分支" in o.headline
    assert "1 条已触发预警" in o.headline
    assert "75%" in o.headline
