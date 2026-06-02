from __future__ import annotations

from graph.driver_shift import DEFAULT_CONTESTED_GAP, contested
from view_models.today_view import (
    AllocationOverview,
    ContestedItem,
    RegimeCluster,
    ShiftItem,
    ShiftsView,
    TodayCard,
    TodayView,
)


def _evidence_count(incoming_edges) -> int:
    return sum(len(e.supporting_evidence) for e in incoming_edges)


def _lean(strength: float) -> str:
    if strength >= 0.55:
        return "偏多"
    if strength <= 0.45:
        return "偏空"
    return "中性"


def _conviction(confidence: float) -> str:
    return "高" if confidence >= 0.66 else ("中" if confidence >= 0.4 else "低")


_NATURE_RANK = {"结构性": 3, "周期性": 2, "情绪事件": 1}


def _quality_phrase(frm: str, to: str, nature: dict) -> str:
    """同向换驱动时的支撑质量判断:结构性最扎实,情绪事件最脆弱。"""
    nf, nt = nature.get(frm), nature.get(to)
    if not nf or not nt:
        return ""
    rf, rt = _NATURE_RANK.get(nf, 2), _NATURE_RANK.get(nt, 2)
    if rf > rt:
        return f"支撑质量↓:由{nf}「{frm}」转向更脆弱的{nt}「{to}」,涨跌更依赖短期因素"
    if rf < rt:
        return f"支撑质量↑:由{nf}「{frm}」转向更扎实的{nt}「{to}」,逻辑更可持续"
    return f"驱动性质相近(都属{nf})"


def _stance(node, incoming_edges, nature: dict | None = None) -> dict:
    """确定性立场:从图谱状态推导(非 LLM)。返回 lean/conviction/challenger/switch_kind/flip_note。"""
    nature = nature or {}
    out = {"lean": _lean(node.strength), "conviction": _conviction(node.confidence),
           "challenger": None, "switch_kind": None, "flip_note": None}
    ranked = sorted(incoming_edges, key=lambda e: e.weight, reverse=True)
    if (len(ranked) >= 2 and _evidence_count(incoming_edges) > 0
            and (ranked[0].weight - ranked[1].weight) < DEFAULT_CONTESTED_GAP and ranked[0].weight > 0):
        leader, runner = ranked[0], ranked[1]
        out["challenger"] = runner.driver_label
        nf, nt = nature.get(leader.driver_label), nature.get(runner.driver_label)
        natures = f"（{nf or '?'} → {nt or '?'}）" if (nf or nt) else ""
        if leader.sign != runner.sign:
            out["switch_kind"] = "方向反转风险"
            out["flip_note"] = f"若主导切到「{runner.driver_label}」(异号){natures},{node.name}方向倾向或反转"
        else:
            out["switch_kind"] = "同向换驱动"
            q = _quality_phrase(leader.driver_label, runner.driver_label, nature)
            out["flip_note"] = f"方向不变,驱动从「{leader.driver_label}」→「{runner.driver_label}」{natures}。{q}"
    return out


def _rank_score(node, incoming_edges, shifting: set[str]) -> float:
    """今日排序:①发生驱动切换 > ②逼近切换 > ③证据量 > ④方向性强度(偏离中性)。

    "逼近切换"只在节点有真实证据时才算 —— 否则种子图里等权的入边会被误判为 contested,
    让首页在没有任何新闻时就堆满假"分歧"。
    """
    ev = _evidence_count(incoming_edges)
    score = 0.0
    if node.id in shifting:
        score += 1000
    if ev > 0 and contested(incoming_edges):
        score += 500
    score += ev * 10
    score += abs(node.strength - 0.5) * 20
    return score


def build_today_view(graph_repo, top_n: int = 7, pinned: list[str] | None = None) -> TodayView:
    graph_repo.seed_if_empty()
    pinned = pinned or []
    assets = [n for n in graph_repo.list_nodes() if n.kind == "asset" and n.status == "active"]
    if not assets:
        return TodayView(available=False)
    shifting = {s["node_id"] for s in graph_repo.list_driver_shifts()}

    scored = []
    for node in assets:
        incoming = graph_repo.incoming_edges(node.id)
        scored.append((node, incoming, _rank_score(node, incoming, shifting)))
    # pinned first, then by score desc
    scored.sort(key=lambda t: (t[0].id not in pinned, -t[2]))

    nature = graph_repo.factor_nature()
    cards = []
    for (n, inc, _) in scored[:top_n]:
        s = _stance(n, inc, nature)
        cards.append(TodayCard(
            asset_id=n.id, name=n.name, dominant_driver=n.dominant_driver, read_line=n.read_line,
            strength=n.strength, confidence=n.confidence, tags_regime=n.tags_regime,
            is_shifting=n.id in shifting, is_contested=contested(inc), evidence_count=_evidence_count(inc),
            lean=s["lean"], conviction=s["conviction"], challenger=s["challenger"],
            switch_kind=s["switch_kind"], flip_note=s["flip_note"],
        ))
    return TodayView(available=True, cards=cards, total_assets=len(assets))


def build_allocation_overview(graph_repo) -> AllocationOverview:
    """跨资产配置速览:按 regime 聚类,每簇分偏多/偏空(确定性,从图谱推导)。"""
    graph_repo.seed_if_empty()
    buckets: dict[str, RegimeCluster] = {}
    for n in graph_repo.list_nodes():
        if n.kind != "asset" or n.status != "active" or not n.tags_regime:
            continue
        c = buckets.setdefault(n.tags_regime, RegimeCluster(regime=n.tags_regime))
        lean = _lean(n.strength)
        if lean == "偏多":
            c.long_names.append(n.name)
        elif lean == "偏空":
            c.short_names.append(n.name)
    clusters = [c for c in buckets.values() if c.long_names or c.short_names]
    return AllocationOverview(available=bool(clusters), clusters=clusters)


def _sign_of(edges, driver_label) -> int | None:
    e = next((x for x in edges if x.driver_label == driver_label), None)
    return e.sign if e is not None else None


def build_shifts_view(graph_repo) -> ShiftsView:
    """分歧预警视图:已切换(driver_shifts) + 正在逼近切换(contested),含方向反转判定与含义。"""
    graph_repo.seed_if_empty()
    nodes = {n.id: n for n in graph_repo.list_nodes()}
    name_by_id = {nid: n.name for nid, n in nodes.items()}
    nature = graph_repo.factor_nature()

    def _nat(d):  # "结构性" -> "(结构性)" else ""
        return f"({nature[d]})" if d in nature else ""

    def _dir(sign):  # 边符号 -> 利多/利空
        return "利多" if (sign or 0) > 0 else ("利空" if sign is not None else "")

    def _lean_of(node_id):
        n = nodes.get(node_id)
        return _lean(n.strength) if n is not None else "中性"

    shifts = []
    for s in sorted(graph_repo.list_driver_shifts(), key=lambda s: s.get("at", ""), reverse=True):
        edges = graph_repo.incoming_edges(s["node_id"])
        fs, ts = _sign_of(edges, s["from_driver"]), _sign_of(edges, s["to_driver"])
        reversal = fs is not None and ts is not None and fs != ts
        name = name_by_id.get(s["node_id"], s["node_id"])
        frm, to = s["from_driver"], s["to_driver"]
        if reversal:
            impl = f"方向反转:主导从「{frm}」{_nat(frm)}切到异号的「{to}」{_nat(to)},{name} 多空逻辑翻转"
        else:
            q = _quality_phrase(frm, to, nature)
            impl = f"同向换驱动:方向不变,驱动由「{frm}」{_nat(frm)}转为「{to}」{_nat(to)}。{q}"
        shifts.append(ShiftItem(node_id=s["node_id"], name=name, from_driver=frm,
                                to_driver=to, at=s["at"], is_reversal=reversal, implication=impl,
                                current_lean=_lean_of(s["node_id"]), from_dir=_dir(fs), to_dir=_dir(ts)))

    contested_items = []
    for node in graph_repo.list_nodes():
        if node.kind != "asset" or node.status != "active":
            continue
        incoming = sorted(graph_repo.incoming_edges(node.id), key=lambda e: e.weight, reverse=True)
        if (len(incoming) >= 2 and _evidence_count(incoming) > 0
                and (incoming[0].weight - incoming[1].weight) < DEFAULT_CONTESTED_GAP and incoming[0].weight > 0):
            leader, runner = incoming[0], incoming[1]
            reversal = leader.sign != runner.sign
            ld, rn = leader.driver_label, runner.driver_label
            if reversal:
                impl = f"异号:若「{rn}」{_nat(rn)}反超「{ld}」{_nat(ld)},{node.name} 方向倾向或反转"
            else:
                impl = f"同向:{_quality_phrase(ld, rn, nature)}" if _quality_phrase(ld, rn, nature) \
                    else f"同向:方向不变,驱动从「{ld}」转向「{rn}」"
            contested_items.append(ContestedItem(
                node_id=node.id, name=node.name, leader=leader.driver_label,
                runner_up=runner.driver_label, gap=round(leader.weight - runner.weight, 3),
                is_reversal=reversal, implication=impl,
                current_lean=_lean(node.strength), from_dir=_dir(leader.sign), to_dir=_dir(runner.sign)))
    available = bool(shifts or contested_items)
    return ShiftsView(available=available, shifts=shifts, contested=contested_items)
