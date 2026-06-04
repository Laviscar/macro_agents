from __future__ import annotations


def _fmt(r) -> str:
    chg = f"（{r.change:+}{r.unit}）" if r.change is not None else ""
    return f"{r.label} {r.value}{r.unit}{chg}（截至 {r.date}）"


def fred_context_block(fred_repo, driver_node_ids: list[str]) -> str:
    """组装注入委员会的 FRED 硬数据文本:该资产驱动因子的实测读数 + 通用宏观背景。
    无任何读数返回 ""。标 [FRED 实测],委员据此引真值、勿编造。"""
    lines: list[str] = []
    seen: set[str] = set()
    for nid in driver_node_ids:
        if nid in seen:
            continue
        seen.add(nid)
        r = fred_repo.reading_for_node(nid)
        if r is not None:
            lines.append(f"  {_fmt(r)}")
    general = fred_repo.general_readings()

    if not lines and not general:
        return ""
    out = ["[FRED 实测,请引用真值、勿编造]"]
    if lines:
        out.append("驱动硬数据:")
        out.extend(lines)
    if general:
        out.append("通用宏观背景:" + " / ".join(_fmt(g) for g in general))
    return "\n".join(out)
