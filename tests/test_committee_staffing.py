import random

from committee.staffing import random_staff

SKILLS = [
    {"id": "rates_curve", "name": "利率与曲线", "persona": "鹰派"},
    {"id": "geopolitics", "name": "地缘风险", "persona": "逆向"},
    {"id": "positioning", "name": "仓位与拥挤度", "persona": "逆向"},
    {"id": "verify", "name": "求证与溯源", "persona": "数据派"},
    {"id": "event_gap", "name": "事件与预期差", "persona": "鸽派"},
    {"id": "liquidity", "name": "流动性追踪", "persona": "鸽派"},
]
PERSONAS = ["鹰派", "鸽派", "逆向", "结构派", "数据派"]


def test_random_respects_seat_count():
    seats = random_staff(4, SKILLS, PERSONAS, rng=random.Random(1))
    assert len(seats) == 4                          # exactly the requested count
    assert all(s.skills[0] in {x["id"] for x in SKILLS} for s in seats)


def test_random_persona_follows_skill_affinity():
    seats = random_staff(6, SKILLS, PERSONAS, rng=random.Random(2))
    by_id = {s["id"]: s["persona"] for s in SKILLS}
    for seat in seats:
        assert seat.persona == by_id[seat.skills[0]]   # persona = skill affinity, not random-order


def test_random_deterministic_with_seed_but_varies_across_seeds():
    a = [(s.persona, tuple(s.skills)) for s in random_staff(3, SKILLS, PERSONAS, rng=random.Random(7))]
    b = [(s.persona, tuple(s.skills)) for s in random_staff(3, SKILLS, PERSONAS, rng=random.Random(7))]
    c = [(s.persona, tuple(s.skills)) for s in random_staff(3, SKILLS, PERSONAS, rng=random.Random(99))]
    assert a == b and a != c


def test_random_count_larger_than_skills_allows_repeats():
    seats = random_staff(8, SKILLS, PERSONAS, rng=random.Random(3))
    assert len(seats) == 8
