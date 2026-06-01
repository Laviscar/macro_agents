from __future__ import annotations

from graph.driver_shift import DEFAULT_CONTESTED_GAP, contested
from view_models.today_view import ContestedItem, ShiftItem, ShiftsView, TodayCard, TodayView


def _evidence_count(incoming_edges) -> int:
    return sum(len(e.supporting_evidence) for e in incoming_edges)


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

    cards = [
        TodayCard(
            asset_id=n.id, name=n.name, dominant_driver=n.dominant_driver, read_line=n.read_line,
            strength=n.strength, confidence=n.confidence, tags_regime=n.tags_regime,
            is_shifting=n.id in shifting, is_contested=contested(inc), evidence_count=_evidence_count(inc),
        )
        for (n, inc, _) in scored[:top_n]
    ]
    return TodayView(available=True, cards=cards, total_assets=len(assets))


def build_shifts_view(graph_repo) -> ShiftsView:
    """分歧预警视图:已切换(driver_shifts) + 正在逼近切换(contested)。"""
    graph_repo.seed_if_empty()
    name_by_id = {n.id: n.name for n in graph_repo.list_nodes()}
    shifts = [
        ShiftItem(node_id=s["node_id"], name=name_by_id.get(s["node_id"], s["node_id"]),
                  from_driver=s["from_driver"], to_driver=s["to_driver"], at=s["at"])
        for s in sorted(graph_repo.list_driver_shifts(), key=lambda s: s.get("at", ""), reverse=True)
    ]
    contested_items = []
    for node in graph_repo.list_nodes():
        if node.kind != "asset" or node.status != "active":
            continue
        incoming = sorted(graph_repo.incoming_edges(node.id), key=lambda e: e.weight, reverse=True)
        if (len(incoming) >= 2 and _evidence_count(incoming) > 0
                and (incoming[0].weight - incoming[1].weight) < DEFAULT_CONTESTED_GAP and incoming[0].weight > 0):
            contested_items.append(ContestedItem(
                node_id=node.id, name=node.name, leader=incoming[0].driver_label,
                runner_up=incoming[1].driver_label, gap=round(incoming[0].weight - incoming[1].weight, 3)))
    available = bool(shifts or contested_items)
    return ShiftsView(available=available, shifts=shifts, contested=contested_items)
