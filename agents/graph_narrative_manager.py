from __future__ import annotations

import json
import re

from pydantic import BaseModel

from graph.driver_shift import DriverShift, detect_shift, dominant_edge
from graph.strength import compute_edge_weight, compute_node_strength
from llm.base import LLMClient, LLMError, LLMMessage
from schemas.graph_edge import GraphEdge
from schemas.graph_node import GraphNode

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_json(text: str) -> dict:
    cleaned = _FENCE.sub("", text).strip()
    return json.loads(cleaned)


class AttributionResult(BaseModel):
    edge_driver: str        # driver_label of the matched incoming edge
    aligns_sign: int        # +1 / -1: does the evidence agree with the edge's structural sign


class GraphNarrativeManager:
    """Drives the narrative graph during consolidation.

    LLM roles: map evidence onto an existing edge (attribute), or propose a
    controlled candidate edge (propose_edge), and write node narration. The
    recompute/shift/dormancy steps are deterministic (no LLM).
    """

    def __init__(self, llm_client: LLMClient | None = None, audit_panel=None) -> None:
        self._llm = llm_client
        # Reserved: the V1.5 AuditPanel will critique driver-shift decisions in a
        # v1.6.x follow-up. Stored here so its env config stays live; not yet invoked.
        self.audit_panel = audit_panel

    # ---- Phase 5: route a news claim to the asset(s) it concerns ----
    def route_assets(self, evidence_claim: str, asset_ids: list[str]) -> list[str] | None:
        """Pick which tracked assets a claim concerns. Returns [] when none apply, or
        None on an LLM/parse failure (so the caller can count failures instead of
        silently treating an error as 'no relevant assets')."""
        if self._llm is None or not asset_ids:
            return []
        system = "You pick which tracked assets a macro news claim concerns. STRICT JSON only."
        user = (
            f"Tracked assets: {asset_ids}\nNews claim: {evidence_claim}\n\n"
            'Return {"assets": [<subset of tracked assets the claim concerns>]}. '
            "Empty list if none apply."
        )
        try:
            resp = self._llm.complete(
                [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
                temperature=0.0, max_tokens=512,
            )
            data = _parse_json(resp.text)
        except (LLMError, ValueError, KeyError):
            return None
        allowed = set(asset_ids)
        return [a for a in (data.get("assets") or []) if a in allowed]

    # ---- Task 13: attribute evidence to an existing edge ----
    def attribute(self, evidence_claim: str, asset_id: str, incoming_edges: list[GraphEdge]) -> AttributionResult | None:
        if self._llm is None or not incoming_edges:
            return None
        drivers = {e.driver_label for e in incoming_edges}
        system = (
            "You map a macro news claim to ONE of an asset's existing driver edges. "
            "Respond STRICT JSON only."
        )
        user = (
            f"Asset: {asset_id}\nCandidate drivers: {sorted(drivers)}\n"
            f"News claim: {evidence_claim}\n\n"
            'Return {"driver_label": <one of the candidates or null>, "aligns_sign": 1 or -1}. '
            "Pick null if the claim does not fit any candidate driver."
        )
        try:
            resp = self._llm.complete(
                [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
                temperature=0.0, max_tokens=512,
            )
            data = _parse_json(resp.text)
        except (LLMError, ValueError, KeyError):
            return None
        driver = data.get("driver_label")
        if driver not in drivers:
            return None
        aligns = int(data.get("aligns_sign", 1))
        return AttributionResult(edge_driver=driver, aligns_sign=1 if aligns >= 0 else -1)

    # ---- Task 14: propose a controlled candidate edge ----
    def propose_edge(self, evidence_claim: str, asset_id: str, vocab: set[str], existing_edge_ids: set[str]) -> GraphEdge | None:
        if self._llm is None:
            return None
        system = (
            "You propose ONE new driver edge for an asset, drawn from a controlled "
            "factor vocabulary. Respond STRICT JSON only."
        )
        user = (
            f"Asset: {asset_id}\nAllowed factor vocabulary: {sorted(vocab)}\n"
            f"News claim: {evidence_claim}\n\n"
            'Return {"src": <factor or asset id>, "dst": "' + asset_id + '", '
            '"sign": 1 or -1, "driver_label": <one factor from the vocabulary>}.'
        )
        try:
            resp = self._llm.complete(
                [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
                temperature=0.0, max_tokens=512,
            )
            data = _parse_json(resp.text)
        except (LLMError, ValueError, KeyError):
            return None
        driver = data.get("driver_label")
        if driver not in vocab:
            return None
        src, dst = data.get("src"), data.get("dst", asset_id)
        if not src:
            return None
        edge_id = f"{src}->{dst}"
        if edge_id in existing_edge_ids:
            return None
        sign = 1 if int(data.get("sign", 1)) >= 0 else -1
        return GraphEdge(id=edge_id, src=src, dst=dst, sign=sign, driver_label=driver, status="candidate")

    # ---- Task 15: recompute node + detect shift (deterministic) ----
    def recompute_node(self, repo, asset_id: str, now) -> DriverShift | None:
        edges = repo.incoming_edges(asset_id)
        # Only edges that received evidence are recomputed from decayed evidence;
        # edges with no evidence keep their seed-prior weight until news arrives.
        for edge in edges:
            if edge.supporting_evidence:
                edge.weight = compute_edge_weight(edge, now)
                repo.save_edge(edge)
        node = repo.get_node(asset_id)
        if node is None:
            return None
        prev_driver = node.dominant_driver
        strength, confidence = compute_node_strength(edges)
        dom = dominant_edge(edges)
        new_driver = dom.driver_label if dom else None
        node.strength, node.confidence = strength, confidence
        node.dominant_driver = new_driver
        node.updated_at = now.isoformat()
        repo.save_node(node)
        return detect_shift(asset_id, prev_driver, new_driver, now.isoformat())

    # ---- Task 16: node narration + tags (LLM) ----
    def narrate_node(self, node: GraphNode, incoming_edges: list[GraphEdge], regimes: set[str]) -> GraphNode:
        if self._llm is None:
            return node
        drivers = ", ".join(f"{e.driver_label}({'+' if e.sign > 0 else '-'},w={e.weight:.2f})" for e in incoming_edges)
        system = "You write a one-line read + tags for an asset narrative node. STRICT JSON only."
        user = (
            f"Asset: {node.name} ({node.id})\nDominant driver: {node.dominant_driver}\n"
            f"Drivers: {drivers}\nDirectional strength (0 short..1 long): {node.strength:.2f}\n"
            f"Allowed regimes: {sorted(regimes)}\n\n"
            'Return {"title": str, "thesis": str, "read_line": str, '
            '"regime": <one allowed regime or null>, "countries": [str]}.'
        )
        try:
            resp = self._llm.complete(
                [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
                temperature=0.0, max_tokens=1024,
            )
            data = _parse_json(resp.text)
        except (LLMError, ValueError, KeyError):
            return node
        node.title = str(data.get("title", "") or "")
        node.thesis = str(data.get("thesis", "") or "")
        node.read_line = str(data.get("read_line", "") or "")
        regime = data.get("regime")
        node.tags_regime = regime if regime in regimes else None
        countries = data.get("countries") or []
        node.tags_countries = [str(c) for c in countries if c]
        return node

    # ---- Task 17: theme-node dormancy ----
    def apply_dormancy(self, repo, now, dormant_days: int = 21) -> None:
        from datetime import datetime

        def _parse(ts: str) -> datetime:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))

        for node in repo.list_nodes():
            if node.resident or node.kind == "factor":
                continue
            edges = repo.incoming_edges(node.id)
            latest = None
            for e in edges:
                for ref in e.supporting_evidence:
                    when = _parse(ref.created_at)
                    latest = when if latest is None or when > latest else latest
            quiet = latest is None or (now - latest).total_seconds() / 86400.0 > dormant_days
            new_status = "dormant" if quiet else "active"
            if node.status != new_status:
                node.status = new_status
                repo.save_node(node)
