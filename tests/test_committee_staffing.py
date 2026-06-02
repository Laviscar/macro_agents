from committee.staffing import auto_staff

SKILLS = [
    {"id": "rates_curve", "name": "利率与曲线"}, {"id": "geopolitics", "name": "地缘风险"},
    {"id": "positioning", "name": "仓位与拥挤度"}, {"id": "verify", "name": "求证与溯源"},
    {"id": "event_gap", "name": "事件与预期差"}, {"id": "liquidity", "name": "流动性追踪"},
]
PERSONAS = ["鹰派", "鸽派", "逆向", "结构派", "数据派"]


def test_matches_driver_to_skill_and_adds_verify():
    seats = auto_staff(["实际利率", "避险地缘"], SKILLS, PERSONAS, max_seats=4)
    assert 1 <= len(seats) <= 4
    all_skills = {s for seat in seats for s in seat.skills}
    assert "rates_curve" in all_skills and "geopolitics" in all_skills   # mapped from drivers
    assert "verify" in all_skills                                        # discipline seat always added
    assert len({seat.persona for seat in seats}) >= 2                    # opposing personas


def test_respects_max_seats():
    seats = auto_staff(["实际利率", "避险地缘", "风险偏好", "央行购金", "通胀预期"], SKILLS, PERSONAS, max_seats=3)
    assert len(seats) <= 3
