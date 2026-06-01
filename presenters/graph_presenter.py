from __future__ import annotations

import json
from pathlib import Path

from graph.driver_shift import dominant_edge
from view_models.graph_view import GraphView, GraphViewEdge, GraphViewNode


def build_graph_view(
    graph_repo,
    *,
    layer: str | None = None,
    focus: str | None = None,
    include_dormant: bool = False,
) -> GraphView:
    """Build the renderer-agnostic world-tree snapshot.

    Seeds the graph if empty so the structure is visible before any news arrives.
    `layer` filters to one layer; `focus` restricts to an asset and its 1-hop incoming
    drivers; dormant theme nodes are hidden unless `include_dormant`.
    """
    graph_repo.seed_if_empty()
    all_nodes = {n.id: n for n in graph_repo.list_nodes()}
    all_edges = graph_repo.list_edges()
    shifting = {s["node_id"] for s in graph_repo.list_driver_shifts()}

    # dominant edge per asset (for highlighting)
    dominant_edge_ids: set[str] = set()
    for nid, node in all_nodes.items():
        if node.kind != "asset":
            continue
        incoming = [e for e in all_edges if e.dst == nid and e.status == "active"]
        dom = dominant_edge(incoming)
        if dom is not None:
            dominant_edge_ids.add(dom.id)

    # choose which node ids to show
    if focus and focus in all_nodes:
        keep = {focus}
        keep |= {e.src for e in all_edges if e.dst == focus and e.status == "active"}
    else:
        keep = set(all_nodes.keys())

    def _visible(node) -> bool:
        if node.id not in keep:
            return False
        if not include_dormant and node.status == "dormant":
            return False
        if layer and node.layer != layer:
            return False
        return True

    visible_ids = {nid for nid, node in all_nodes.items() if _visible(node)}
    nodes = [
        GraphViewNode(
            id=n.id, name=n.name, kind=n.kind, layer=n.layer, status=n.status,
            strength=n.strength, confidence=n.confidence, dominant_driver=n.dominant_driver,
            tags_regime=n.tags_regime, tags_countries=list(n.tags_countries),
            title=n.title, read_line=n.read_line, is_shifting=n.id in shifting,
        )
        for nid, n in all_nodes.items() if nid in visible_ids
    ]
    edges = [
        GraphViewEdge(
            src=e.src, dst=e.dst, sign=e.sign, driver_label=e.driver_label,
            weight=e.weight, is_dominant=e.id in dominant_edge_ids,
        )
        for e in all_edges
        if e.status == "active" and e.src in visible_ids and e.dst in visible_ids
    ]
    return GraphView(nodes=nodes, edges=edges)


_LAYER_FILL = {
    "anchor": "#ffd9d9",       # 宏观锚
    "asset_class": "#d9e8ff",  # 大类
    "theme": "#d9ffe0",        # 主题
    "factor": "#eeeeee",       # 因子
}


def graph_to_dot(view) -> str:
    """Render a GraphView as Graphviz DOT (consumed by st.graphviz_chart).

    Nodes colored by layer; shifting assets get a red bold border; edge color =
    sign (+green/-red), width ~ weight, dominant driver edges are bold.
    """
    lines = ["digraph G {", "rankdir=LR;", 'node [style=filled, shape=box, fontname="Helvetica"];']
    for n in view.nodes:
        fill = _LAYER_FILL.get(n.layer, "#ffffff")
        label = n.name + (f"\\n[{n.dominant_driver}]" if n.dominant_driver else "")
        extra = ', color="#d32f2f", penwidth=3' if n.is_shifting else ""
        lines.append(f'"{n.id}" [label="{label}", fillcolor="{fill}"{extra}];')
    for e in view.edges:
        color = "#2e7d32" if e.sign > 0 else "#c62828"
        pen = 1.0 + e.weight * 4.0
        style = "bold" if e.is_dominant else "solid"
        lines.append(f'"{e.src}" -> "{e.dst}" [label="{e.driver_label}", color="{color}", penwidth={pen:.1f}, style={style}];')
    lines.append("}")
    return "\n".join(lines)


def node_shift_history(graph_repo, node_id: str) -> list[dict]:
    """Per-node driver-shift history (newest first) — the v1.6 '演变' for one asset."""
    rows = [s for s in graph_repo.list_driver_shifts() if s.get("node_id") == node_id]
    return sorted(rows, key=lambda s: s.get("at", ""), reverse=True)


def export_graph_json(graph_repo, path: str | Path) -> None:
    """Write the full graph as JSON — the stable contract a future fancy frontend reads."""
    view = build_graph_view(graph_repo, include_dormant=True)
    Path(path).write_text(json.dumps(view.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
