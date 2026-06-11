from __future__ import annotations

from datetime import datetime
from pathlib import Path

from agents.analyst import AnalystAgent
from agents.news_sorter import NewsSorterAgent
from agents.narrative_manager import NarrativeManagerAgent
from agents.triage import TriageAgent
from harness.coordinator import _load_or_build_resource_card, load_narrative_state, persist_narrative_state
from pipelines.narrative_update import update_from_evidence
from repositories.news_repository import SQLiteNewsRepository
from schemas.fred import FredReading
from schemas.graph_edge import EdgeEvidenceRef
from sources.fred import FredError
from utils.clock import now_iso
from utils.io import read_json, write_json

_CONTEXT = {"target_main_narrative_id": "main_default"}


def triage_pending(
    repository: SQLiteNewsRepository,
    triage_agent: TriageAgent,
    sorter: NewsSorterAgent,
    limit: int = 20,
    since: str | None = None,
    newest_first: bool = False,
) -> dict:
    """pending_sort -> pending_analysis (important) | skipped (not important)."""
    important = skipped = errors = 0
    for row in repository.list_news_by_status("pending_sort", limit=limit, since=since, newest_first=newest_first):
        nid = int(row["id"])
        try:
            card = _load_or_build_resource_card(row, sorter)
            keep = triage_agent.is_important(card)
            repository.save_resource_card(nid, card, status="pending_analysis" if keep else "skipped")
            important += int(keep)
            skipped += int(not keep)
        except Exception as exc:
            repository.mark_error(nid, str(exc))
            errors += 1
    return {"important": important, "skipped": skipped, "errors": errors}


def analyze_pending(
    repository: SQLiteNewsRepository,
    analyst: AnalystAgent,
    limit: int = 10,
    since: str | None = None,
    newest_first: bool = False,
) -> dict:
    """pending_analysis -> analyzed (+ analysis_cards / evidence_records)."""
    analyzed = errors = 0
    sorter = NewsSorterAgent()
    for row in repository.list_news_by_status("pending_analysis", limit=limit, since=since, newest_first=newest_first):
        nid = int(row["id"])
        try:
            card = _load_or_build_resource_card(row, sorter)
            analysis_card = analyst.analyze(card, context=_CONTEXT)
            evidence = analyst.extract_evidence(analysis_card, context=_CONTEXT)
            repository.save_analysis_bundle(nid, analysis_card, evidence)
            analyzed += 1
        except Exception as exc:
            repository.mark_error(nid, str(exc))
            errors += 1
    return {"analyzed": analyzed, "errors": errors}


def consolidate(
    repository: SQLiteNewsRepository,
    narrative_manager: NarrativeManagerAgent,
    storage_root: str | Path,
    run_state_path: str | Path,
) -> dict:
    """Digest evidence created since the last consolidation watermark into the narrative."""
    state_doc = read_json(run_state_path, default={}) or {}
    watermark = state_doc.get("last_consolidation_at", "")

    evidence_list = repository.get_evidence_since(watermark)
    if not evidence_list:
        return {"consolidated_evidence": 0}

    analysis_cards = repository.get_analysis_cards_since(watermark)
    prior_state = load_narrative_state(storage_root)
    state = update_from_evidence(
        evidence_list=evidence_list,
        analysis_cards=analysis_cards,
        agent=narrative_manager,
        state=prior_state,
    )
    read_line = narrative_manager.generate_read_line(state["main_narrative"], evidence_list)
    updates = {"read_line": read_line}
    if not state["main_narrative"].core_claims or state["main_narrative"].core_claims == ["待定义"]:
        updates["core_claims"] = [read_line]
    state["main_narrative"] = state["main_narrative"].model_copy(update=updates)

    persist_narrative_state(state, storage_root)
    state_doc["last_consolidation_at"] = now_iso()
    write_json(run_state_path, state_doc)
    return {"consolidated_evidence": len(evidence_list)}


def fetch_fred_readings(fred_repo, fred_client, series_config: list[dict]) -> dict:
    """拉取 FRED 硬数据写入读数库(0 LLM,不改图)。失败序列跳过+计数。"""
    ok = errors = 0
    for s in series_config:
        try:
            value, date, prev = fred_client.fetch_observation(s["series_id"])
        except FredError:
            errors += 1
            continue
        fred_repo.save_reading(FredReading(
            series_id=s["series_id"], label=s.get("label", s["series_id"]), unit=s.get("unit", ""),
            node_id=s.get("node_id"), value=value, date=date, prev=prev,
            change=(round(value - prev, 4) if prev is not None else None), fetched_at=now_iso()))
        ok += 1
    return {"fred_ok": ok, "fred_errors": errors}


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _evaluate_committee(committee_repo, graph_repo, trigger_levels, velocity_delta: float,
                        reversal_only: bool = True) -> int:
    """Flag committee pending convocations from the current graph (no LLM). Runs every
    consolidation cycle — even when there is no new evidence — since contested conditions
    persist. Returns the number of pendings created this cycle."""
    if committee_repo is None:
        return 0
    from committee.trigger import evaluate_assets
    tstate = committee_repo.load_trigger_state()
    pendings = evaluate_assets(graph_repo, tstate, trigger_levels or [0.60, 0.75, 0.90],
                               velocity_delta, reversal_only=reversal_only)
    committee_repo.save_trigger_state(tstate)
    # 同一资产出现新待召开 → 旧的标记 expired(保留),再存新的
    for aid in {p.asset_id for p in pendings}:
        new_ct = next(p.created_at for p in pendings if p.asset_id == aid)
        committee_repo.supersede_pending(aid, new_ct)
    for p in pendings:
        committee_repo.save_pending(p)
    return len(pendings)


def consolidate_graph(
    repository: SQLiteNewsRepository,
    graph_repo,
    graph_manager,
    vocab: set[str],
    regimes: set[str],
    run_state_path: str | Path,
    now_fn=now_iso,
    max_evidence: int = 50,
    committee_repo=None,
    trigger_levels: list[float] | None = None,
    velocity_delta: float = 0.10,
    committee_reversal_only: bool = True,
) -> dict:
    """v1.6 consolidation: route new evidence to assets, attribute to driver edges
    (or propose candidate edges), recompute node strength + dominant driver, persist
    driver shifts, narrate, and apply theme dormancy.

    Watermark-incremental and **budget-bounded**: processes at most `max_evidence`
    of the oldest-unseen evidence per run, advancing the watermark only to the last
    item actually processed — so a large backlog is consumed in capped chunks across
    runs instead of one budget-blowing pass. Returns failure counts so silent LLM
    errors are visible."""
    graph_repo.seed_if_empty()
    state_doc = read_json(run_state_path, default={}) or {}
    watermark = state_doc.get("last_consolidation_at", "")
    evidence_list = repository.get_evidence_since(watermark)  # ascending by created_at
    if not evidence_list:
        # No new evidence to consolidate, but the committee trigger must STILL evaluate
        # the current graph (contested conditions persist across cycles).
        pending = _evaluate_committee(committee_repo, graph_repo, trigger_levels, velocity_delta, committee_reversal_only)
        return {"consolidated_evidence": 0, "shifts": 0, "touched": 0, "route_errors": 0,
                "unrouted": 0, "candidates": 0, "remaining": 0, "committee_pending": pending}

    batch = evidence_list[:max_evidence]
    now_dt = _parse_iso(now_fn())
    asset_ids = [n.id for n in graph_repo.list_nodes() if n.kind == "asset"]
    touched: set[str] = set()
    route_errors = unrouted = candidates = 0

    for ev in batch:
        routed = graph_manager.route_assets(ev.claim, asset_ids)
        if routed is None:        # LLM/parse failure — count it, don't pretend it's "none"
            route_errors += 1
            continue
        if not routed:
            unrouted += 1
            continue
        for aid in routed:
            edges = graph_repo.incoming_edges(aid)
            result = graph_manager.attribute(ev.claim, aid, edges)
            if result is not None:
                edge = next(e for e in edges if e.driver_label == result.edge_driver)
                edge.supporting_evidence.append(EdgeEvidenceRef(
                    evidence_id=ev.id, created_at=ev.created_at,
                    contribution=min(1.0, float(ev.strength) * float(ev.confidence))))
                graph_repo.save_edge(edge)
            else:
                existing = {e.id for e in graph_repo.list_edges()} | {c.id for c in graph_repo.list_candidates()}
                cand = graph_manager.propose_edge(ev.claim, aid, vocab, existing)
                if cand is not None:
                    graph_repo.add_candidate_edge(cand)
                    candidates += 1
            touched.add(aid)

    shifts = 0
    for aid in touched:
        shift = graph_manager.recompute_node(graph_repo, aid, now_dt)
        if shift is not None:
            graph_repo.save_driver_shift(shift)
            shifts += 1
        node = graph_repo.get_node(aid)
        if node is not None:
            graph_manager.narrate_node(node, graph_repo.incoming_edges(aid), regimes)
            graph_repo.save_node(node)

    graph_manager.apply_dormancy(graph_repo, now_dt)

    # v1.7: evaluate committee triggers on the updated graph (flag-only, no LLM, human-gated convening).
    pending_count = _evaluate_committee(committee_repo, graph_repo, trigger_levels, velocity_delta, committee_reversal_only)

    # advance watermark only to the last processed item, so the rest is picked up next run
    state_doc["last_consolidation_at"] = batch[-1].created_at
    write_json(run_state_path, state_doc)
    return {"consolidated_evidence": len(batch), "shifts": shifts, "touched": len(touched),
            "route_errors": route_errors, "unrouted": unrouted, "candidates": candidates,
            "remaining": len(evidence_list) - len(batch), "committee_pending": pending_count}
