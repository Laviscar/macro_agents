from __future__ import annotations

from pathlib import Path

from agents.analyst import AnalystAgent
from agents.news_sorter import NewsSorterAgent
from agents.narrative_manager import NarrativeManagerAgent
from agents.triage import TriageAgent
from harness.coordinator import _load_or_build_resource_card, load_narrative_state, persist_narrative_state
from pipelines.narrative_update import update_from_evidence
from repositories.news_repository import SQLiteNewsRepository
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
