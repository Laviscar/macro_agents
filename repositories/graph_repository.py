from __future__ import annotations

import json
from pathlib import Path

import yaml

from schemas.graph_edge import GraphEdge
from schemas.graph_node import GraphNode


def _edge_id(src: str, dst: str) -> str:
    return f"{src}->{dst}"


def _safe_filename(edge_id: str) -> str:
    """Edge ids contain '->' (and possibly '/' from tickers); make them filesystem-safe."""
    return edge_id.replace("->", "__").replace("/", "_")


class GraphRepository:
    """File-backed store for the narrative driver graph.

    Nodes and edges are one-JSON-per-entity (matching the repo's existing
    storage convention). On first run, seeds from config/*.yaml.
    """

    def __init__(self, storage_root: str | Path, config_dir: str | Path = "config") -> None:
        self.storage_root = Path(storage_root)
        self.config_dir = Path(config_dir)
        self.nodes_dir = self.storage_root / "graph_nodes"
        self.edges_dir = self.storage_root / "graph_edges"
        self.candidates_dir = self.storage_root / "candidate_edges"
        self.shifts_dir = self.storage_root / "driver_shifts"
        for d in (self.nodes_dir, self.edges_dir, self.candidates_dir, self.shifts_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---- seeding ----
    def seed_if_empty(self) -> None:
        if any(self.nodes_dir.glob("*.json")):
            return
        vocab = yaml.safe_load((self.config_dir / "driver_vocabulary.yaml").read_text(encoding="utf-8"))
        assets = yaml.safe_load((self.config_dir / "narrative_assets.yaml").read_text(encoding="utf-8"))["assets"]
        seed_edges = yaml.safe_load((self.config_dir / "transmission_seed.yaml").read_text(encoding="utf-8"))["edges"]

        # asset nodes
        for a in assets:
            self.save_node(GraphNode(
                id=a["id"], kind="asset", name=a["name"], layer=a["layer"],
                ticker=a.get("ticker"), resident=a.get("resident", False),
                tags_countries=a.get("default_countries", []),
            ))
        # factor nodes: any seed src that is a vocabulary factor
        factors = set(vocab["factors"])
        used_factors = {e["src"] for e in seed_edges if e["src"] in factors}
        for f in used_factors:
            self.save_node(GraphNode(id=f, kind="factor", name=f, layer="factor", resident=False))
        # edges
        for e in seed_edges:
            edge = GraphEdge(
                id=_edge_id(e["src"], e["dst"]), src=e["src"], dst=e["dst"],
                sign=e["sign"], driver_label=e["driver_label"], weight=float(e.get("init_weight", 0.0)),
                status="active",
            )
            self.save_edge(edge)

    # ---- node CRUD ----
    def save_node(self, node: GraphNode) -> None:
        (self.nodes_dir / f"{_safe_filename(node.id)}.json").write_text(
            node.model_dump_json(), encoding="utf-8")

    def get_node(self, node_id: str) -> GraphNode | None:
        path = self.nodes_dir / f"{_safe_filename(node_id)}.json"
        if not path.exists():
            return None
        return GraphNode.model_validate_json(path.read_text(encoding="utf-8"))

    def list_nodes(self) -> list[GraphNode]:
        return [GraphNode.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(self.nodes_dir.glob("*.json"))]

    # ---- edge CRUD ----
    def save_edge(self, edge: GraphEdge) -> None:
        (self.edges_dir / f"{_safe_filename(edge.id)}.json").write_text(
            edge.model_dump_json(), encoding="utf-8")

    def get_edge(self, edge_id: str) -> GraphEdge | None:
        path = self.edges_dir / f"{_safe_filename(edge_id)}.json"
        if not path.exists():
            return None
        return GraphEdge.model_validate_json(path.read_text(encoding="utf-8"))

    def list_edges(self) -> list[GraphEdge]:
        return [GraphEdge.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(self.edges_dir.glob("*.json"))]

    def incoming_edges(self, dst: str) -> list[GraphEdge]:
        return [e for e in self.list_edges() if e.dst == dst and e.status == "active"]

    def assets_with_new_evidence(self, since: str) -> set[str]:
        """Asset ids whose incoming edges received evidence at/after `since`."""
        hit: set[str] = set()
        for e in self.list_edges():
            if any(ref.created_at >= since for ref in e.supporting_evidence):
                hit.add(e.dst)
        return hit

    # ---- candidate edges ----
    def add_candidate_edge(self, edge: GraphEdge) -> None:
        edge.status = "candidate"
        (self.candidates_dir / f"{_safe_filename(edge.id)}.json").write_text(
            edge.model_dump_json(), encoding="utf-8")

    def list_candidates(self) -> list[GraphEdge]:
        return [GraphEdge.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(self.candidates_dir.glob("*.json"))]

    def promote_candidate(self, edge_id: str) -> GraphEdge | None:
        path = self.candidates_dir / f"{_safe_filename(edge_id)}.json"
        if not path.exists():
            return None
        edge = GraphEdge.model_validate_json(path.read_text(encoding="utf-8"))
        edge.status = "active"
        self.save_edge(edge)
        path.unlink()
        return edge

    def reject_candidate(self, edge_id: str) -> None:
        path = self.candidates_dir / f"{_safe_filename(edge_id)}.json"
        if path.exists():
            path.unlink()

    # ---- driver shifts (= the new "分歧预警") ----
    def save_driver_shift(self, shift) -> None:
        name = _safe_filename(f"{shift.node_id}_{shift.at}")
        (self.shifts_dir / f"{name}.json").write_text(
            shift.model_dump_json() if hasattr(shift, "model_dump_json") else json.dumps(shift),
            encoding="utf-8")

    def list_driver_shifts(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(self.shifts_dir.glob("*.json"))]
