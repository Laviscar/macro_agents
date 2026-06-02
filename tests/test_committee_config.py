import yaml
from pathlib import Path

CFG = Path("config")


def _load(n):
    return yaml.safe_load((CFG / n).read_text(encoding="utf-8"))


def test_skill_library_has_12_and_personas():
    d = _load("committee_skills.yaml")
    assert len(d["skills"]) == 12
    assert {"verify", "rates_curve", "event_gap"} <= {s["id"] for s in d["skills"]}
    assert "鹰派" in d["personas"] and "鸽派" in d["personas"]
    # every skill carries an affinity persona drawn from the persona vocabulary
    personas = set(d["personas"])
    assert all(s.get("persona") in personas for s in d["skills"])


def test_committee_seats_reference_valid_skills_and_personas():
    skills = {s["id"] for s in _load("committee_skills.yaml")["skills"]}
    personas = set(_load("committee_skills.yaml")["personas"])
    cm = _load("committee.yaml")
    seats = cm["default_seats"] + [s for t in cm["templates"] for s in t["seats"]]
    for seat in seats:
        assert seat["persona"] in personas, seat
        assert set(seat["skills"]) <= skills, seat
