from __future__ import annotations

import random

from schemas.committee import CommitteeSeat

# 驱动(driver_label)→ 该用哪个分析 skill 的启发式映射
_DRIVER_SKILL = {
    "实际利率": "rates_curve", "政策利率": "rates_curve", "收益率曲线": "rates_curve",
    "通胀预期": "event_gap", "增长预期": "event_gap",
    "美元流动性": "liquidity", "全球流动性": "liquidity",
    "风险偏好": "positioning", "信用风险": "positioning",
    "避险地缘": "geopolitics",
    "央行购金": "correlation", "制造业周期": "correlation",
    "财政赤字供给": "policy", "中国增长政策": "policy",
    "AI资本开支": "valuation", "能源供给": "vol_structure",
}


def _persona_of(skill: dict, personas: list[str]) -> str:
    """skill 的亲和人格(committee_skills.yaml 的 persona 字段);缺失则回退。"""
    return skill.get("persona") or (personas[0] if personas else "结构派")


def auto_staff(driver_labels: list[str], skills: list[dict], personas: list[str], max_seats: int = 5) -> list[CommitteeSeat]:
    """规则化组阵(0 LLM):按竞争驱动匹配 skill,**人格按 skill 的亲和人格分配**(利率→鹰、
    流动性→鸽、拥挤→逆向…),总是追加一个求证席位,截到 max_seats。可被用户在 UI 手改。"""
    by_id = {s["id"]: s for s in skills}
    chosen_skills: list[str] = []
    for d in driver_labels:
        sid = _DRIVER_SKILL.get(d)
        if sid and sid in by_id and sid not in chosen_skills:
            chosen_skills.append(sid)

    seats: list[CommitteeSeat] = []
    for i, sid in enumerate(chosen_skills):
        if len(seats) >= max_seats - 1:    # leave room for the verify seat
            break
        persona = _persona_of(by_id[sid], personas)
        seats.append(CommitteeSeat(name=f"{persona}-{sid}", persona=persona,
                                   llm_tier=f"auditor_{(i % 3) + 1}", skills=[sid]))

    # 始终追加一个"求证与溯源"纪律席位
    if "verify" in by_id and len(seats) < max_seats:
        seats.append(CommitteeSeat(name="求证", persona=_persona_of(by_id["verify"], personas),
                                   llm_tier=f"auditor_{(len(seats) % 3) + 1}", skills=["verify"]))
    return seats[:max_seats]


def random_staff(n_seats: int, skills: list[dict], personas: list[str],
                 rng: random.Random | None = None) -> list[CommitteeSeat]:
    """随机组阵,但**只随机"谁/什么人格/什么 skill",席位数固定为 n_seats**(由人工设定,
    不随机)。每席随机一个 skill(尽量不重) + 随机一个人格。rng 可注入以便测试。"""
    rng = rng or random.Random()
    n = max(1, int(n_seats))
    ids = [s["id"] for s in skills]
    if not ids or not personas:
        return []
    picks = rng.sample(ids, min(n, len(ids)))
    while len(picks) < n:                  # n 超过 skill 数时允许重复
        picks.append(rng.choice(ids))
    seats: list[CommitteeSeat] = []
    for i, sid in enumerate(picks):
        persona = rng.choice(personas)
        seats.append(CommitteeSeat(name=f"{persona}-{sid}", persona=persona,
                                   llm_tier=f"auditor_{(i % 3) + 1}", skills=[sid]))
    return seats
