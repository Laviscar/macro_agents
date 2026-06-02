import random

from committee.staffing import auto_staff, random_staff

SKILLS = [
    {"id": "rates_curve", "name": "利率与曲线", "persona": "鹰派"},
    {"id": "geopolitics", "name": "地缘风险", "persona": "逆向"},
    {"id": "positioning", "name": "仓位与拥挤度", "persona": "逆向"},
    {"id": "verify", "name": "求证与溯源", "persona": "数据派"},
    {"id": "event_gap", "name": "事件与预期差", "persona": "鸽派"},
    {"id": "liquidity", "name": "流动性追踪", "persona": "鸽派"},
]
PERSONAS = ["鹰派", "鸽派", "逆向", "结构派", "数据派"]


# --- auto_staff: affinity-based personas ---
def test_persona_follows_skill_affinity_not_order():
    seats = auto_staff(["实际利率", "避险地缘"], SKILLS, PERSONAS, max_seats=4)
    by_skill = {s.skills[0]: s.persona for s in seats}
    assert by_skill["rates_curve"] == "鹰派"        # affinity, not i%5
    assert by_skill["geopolitics"] == "逆向"
    assert by_skill["verify"] == "数据派"            # discipline seat always added


def test_auto_respects_max_seats():
    seats = auto_staff(["实际利率", "避险地缘", "风险偏好", "央行购金", "通胀预期"], SKILLS, PERSONAS, max_seats=3)
    assert len(seats) <= 3


# --- random_staff: respects seat count, randomizes who ---
def test_random_respects_seat_count():
    seats = random_staff(4, SKILLS, PERSONAS, rng=random.Random(1))
    assert len(seats) == 4                          # exactly the requested count
    assert all(s.persona in PERSONAS for s in seats)
    assert all(s.skills[0] in {x["id"] for x in SKILLS} for s in seats)


def test_random_deterministic_with_seed_but_varies_across_seeds():
    a = [(s.persona, tuple(s.skills)) for s in random_staff(3, SKILLS, PERSONAS, rng=random.Random(7))]
    b = [(s.persona, tuple(s.skills)) for s in random_staff(3, SKILLS, PERSONAS, rng=random.Random(7))]
    c = [(s.persona, tuple(s.skills)) for s in random_staff(3, SKILLS, PERSONAS, rng=random.Random(99))]
    assert a == b           # same seed -> same lineup
    assert a != c           # different seed -> different lineup (random who, fixed count)


def test_random_count_larger_than_skills_allows_repeats():
    seats = random_staff(8, SKILLS, PERSONAS, rng=random.Random(3))
    assert len(seats) == 8  # n>skills still yields exactly n
