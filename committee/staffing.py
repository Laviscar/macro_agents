from __future__ import annotations

import random

from schemas.committee import CommitteeSeat


def _persona_of(skill: dict, personas: list[str]) -> str:
    """skill 的亲和人格(committee_skills.yaml 的 persona 字段);缺失则回退。"""
    return skill.get("persona") or (personas[0] if personas else "结构派")


def random_staff(n_seats: int, skills: list[dict], personas: list[str],
                 rng: random.Random | None = None) -> list[CommitteeSeat]:
    """随机组阵:**只随机"填哪些 skill 视角",席位数固定为 n_seats**(人工设定,不随机)。
    每席的人格跟随该 skill 的亲和人格(利率→鹰、流动性→鸽、求证/量价→数据派…),不乱配。
    rng 可注入以便测试。"""
    rng = rng or random.Random()
    n = max(1, int(n_seats))
    by_id = {s["id"]: s for s in skills}
    ids = list(by_id)
    if not ids:
        return []
    picks = rng.sample(ids, min(n, len(ids)))
    while len(picks) < n:                  # n 超过 skill 数时允许重复
        picks.append(rng.choice(ids))
    seats: list[CommitteeSeat] = []
    for i, sid in enumerate(picks):
        persona = _persona_of(by_id[sid], personas)
        seats.append(CommitteeSeat(name=f"{persona}-{sid}", persona=persona,
                                   llm_tier=f"auditor_{(i % 3) + 1}", skills=[sid]))
    return seats
