from __future__ import annotations

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


def auto_staff(driver_labels: list[str], skills: list[dict], personas: list[str], max_seats: int = 5) -> list[CommitteeSeat]:
    """规则化组阵(0 LLM):按竞争驱动匹配 skill,轮转分配对立人格,总是追加一个求证席位,
    截到 max_seats。结果可被用户在 UI 手改(人在环)。"""
    skill_ids = {s["id"] for s in skills}
    chosen_skills: list[str] = []
    for d in driver_labels:
        sid = _DRIVER_SKILL.get(d)
        if sid and sid in skill_ids and sid not in chosen_skills:
            chosen_skills.append(sid)

    seats: list[CommitteeSeat] = []
    for i, sid in enumerate(chosen_skills):
        if len(seats) >= max_seats - 1:    # leave room for the verify seat
            break
        persona = personas[i % len(personas)] if personas else "结构派"
        seats.append(CommitteeSeat(name=f"{persona}-{sid}", persona=persona,
                                   llm_tier=f"auditor_{(i % 3) + 1}", skills=[sid]))

    # 始终追加一个"求证与溯源"纪律席位
    if "verify" in skill_ids and len(seats) < max_seats:
        vp = personas[len(seats) % len(personas)] if personas else "数据派"
        seats.append(CommitteeSeat(name="求证", persona=vp,
                                   llm_tier=f"auditor_{(len(seats) % 3) + 1}", skills=["verify"]))
    return seats[:max_seats]
