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


def test_duplicate_claim_alerts_deduped_keep_highest(tmp_path):
    _seed(tmp_path)
    # 20 alerts on the SAME claim+branch (the old per-tick spam) — must collapse to one
    for i in range(20):
        _write(tmp_path / "alerts" / f"dup{i}.json", {
            "id": f"dup{i}", "main_narrative_id": "main_default", "branch_narrative_id": "b1",
            "challenged_claim": "主线被伊朗变量挑战", "challenge_probability": 0.50 + i * 0.001,
            "key_triggers": [], "created_at": f"2026-05-30T19:{i:02d}:00Z",
        })
    o = build_challenges_overview(tmp_path)
    same_claim = [a for a in o.alerts if a.challenged_claim == "主线被伊朗变量挑战"]
    assert len(same_claim) == 1                       # collapsed
    assert same_claim[0].challenge_probability == 0.75  # highest instance kept
    assert o.total_alerts == 1


def test_alerts_capped_at_eight(tmp_path):
    _seed(tmp_path)
    for i in range(15):  # 15 distinct claims
        _write(tmp_path / "alerts" / f"c{i}.json", {
            "id": f"c{i}", "branch_narrative_id": "b1",
            "challenged_claim": f"claim-{i}", "challenge_probability": 0.10 + i * 0.01,
            "created_at": "2026-05-30T20:00:00Z",
        })
    o = build_challenges_overview(tmp_path)
    assert len(o.alerts) == 8                          # capped
    assert o.total_alerts == 16                         # 15 distinct + original seed claim
    assert o.alerts[0].challenge_probability >= o.alerts[-1].challenge_probability  # prob desc


def test_duplicate_title_branches_deduped(tmp_path):
    _seed(tmp_path)
    # three branches sharing one title — keep the highest-probability
    for i, p in enumerate([0.30, 0.55, 0.20]):
        _write(tmp_path / "branch_narrative_state" / f"dupb{i}.json", {
            "id": f"dupb{i}", "title": "重复标题分支", "status": "seed",
            "challenge_probability": p, "branch_strength": 0.1,
            "core_claims": [], "key_triggers": [], "supporting_evidence": [],
        })
    o = build_challenges_overview(tmp_path)
    dup = [c for c in o.challenges if c.title == "重复标题分支"]
    assert len(dup) == 1 and dup[0].challenge_probability == 0.55
    assert o.total_challenges == 3                       # 伊朗机会窗口 + 低概率分支 + 重复标题分支
