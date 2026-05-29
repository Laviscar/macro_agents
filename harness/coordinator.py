from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agents.analyst import AnalystAgent
from agents.narrative_manager import NarrativeManagerAgent
from agents.news_sorter import NewsSorterAgent
from harness.budget import BudgetConfig, BudgetGuard
from harness.loop import LoopResult, NarrativeLoopEngine
from harness.policy import PolicyEngine, RiskLevel
from harness.runtime import BaseTool, ToolResult, ToolRuntime
from harness.session_store import HarnessSessionStore
from pipelines.narrative_update import update_from_evidence
from repositories.news_repository import SQLiteNewsRepository
from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence
from schemas.resource_card import ResourceCard
from utils.io import ensure_dir, write_model, write_models

_DEFAULT_STORAGE_ROOT = Path("storage")


@dataclass
class TaskInput:
    news_item_ids: list[int]
    task_description: str = ""
    time_budget_seconds: float = 300.0


def _load_or_build_resource_card(row: dict, sorter: NewsSorterAgent) -> ResourceCard:
    existing = row.get("resource_card_json")
    if existing:
        return ResourceCard.model_validate_json(existing)
    raw_payload = json.loads(row["raw_payload_json"])
    payload = dict(raw_payload)
    payload.setdefault("source", row["source_name"])
    payload.setdefault("url", row["url"])
    payload.setdefault("title", row["title"])
    payload.setdefault("summary", row["summary"])
    payload.setdefault("timestamp", row["published_at"] or row["fetched_at"])
    return sorter.process(payload)


class SortAndAnalyzeTool(BaseTool):
    name = "sort_and_analyze"
    risk_level = RiskLevel.LOW
    is_concurrency_safe = True

    def __init__(
        self,
        repository: SQLiteNewsRepository,
        sorter: NewsSorterAgent,
        analyst: AnalystAgent,
    ) -> None:
        self.repository = repository
        self.sorter = sorter
        self.analyst = analyst

    def execute(self, input: dict) -> ToolResult:
        news_item_ids: list[int] = input["news_item_ids"]
        analysis_cards: list[AnalysisCard] = []
        evidence_list: list[Evidence] = []
        processed = 0
        skipped = 0

        context = {"target_main_narrative_id": "main_default"}
        for nid in news_item_ids:
            row = self.repository.get_news_item(nid)
            if row is None:
                continue
            processed += 1
            resource_card = _load_or_build_resource_card(row, self.sorter)
            if not resource_card.route_to_analysis:
                skipped += 1
                continue
            card = self.analyst.analyze(resource_card, context=context)
            evidence = self.analyst.extract_evidence(card, context=context)
            analysis_cards.append(card)
            evidence_list.extend(evidence)

        return ToolResult(
            tool_name=self.name,
            success=True,
            output={
                "analysis_cards": analysis_cards,
                "evidence_list": evidence_list,
                "processed": processed,
                "skipped": skipped,
            },
        )


class UpdateNarrativeTool(BaseTool):
    name = "update_narrative"
    risk_level = RiskLevel.MEDIUM
    is_concurrency_safe = False

    def __init__(
        self,
        narrative_manager: NarrativeManagerAgent,
        storage_root: Path,
    ) -> None:
        self.narrative_manager = narrative_manager
        self.storage_root = storage_root

    def execute(self, input: dict) -> ToolResult:
        evidence_list: list[Evidence] = input["evidence_list"]
        analysis_cards: list[AnalysisCard] = input["analysis_cards"]

        state = update_from_evidence(
            evidence_list=evidence_list,
            analysis_cards=analysis_cards,
            agent=self.narrative_manager,
            state=None,  # Phase 1: fresh state per run
        )

        main_narrative = state["main_narrative"]
        ensure_dir(self.storage_root / "main_narrative_state")
        write_model(
            self.storage_root / "main_narrative_state" / f"{main_narrative.id}.json",
            main_narrative,
        )
        write_models(self.storage_root / "branch_narrative_state", state["branches"])
        write_models(self.storage_root / "narrative_commits", state["commits"])
        write_models(self.storage_root / "alerts", state["alerts"])
        write_models(self.storage_root / "scenarios", state["scenarios"])

        return ToolResult(
            tool_name=self.name,
            success=True,
            output={
                "main_narrative_id": main_narrative.id,
                "branches_count": len(state["branches"]),
                "commits_count": len(state["commits"]),
            },
        )


class HarnessCoordinator:
    def __init__(
        self,
        db_path: str | Path,
        storage_root: str | Path = _DEFAULT_STORAGE_ROOT,
    ) -> None:
        self.db_path = Path(db_path)
        self.storage_root = Path(storage_root)
        self.session_store = HarnessSessionStore(self.db_path)
        self.repository = SQLiteNewsRepository(self.db_path)
        self._sorter = NewsSorterAgent()
        self._analyst = AnalystAgent()
        self._narrative_manager = NarrativeManagerAgent()

    def run_task(self, task_input: TaskInput) -> LoopResult:
        session_id = self.session_store.create_session(
            task_description=task_input.task_description,
            news_item_ids=task_input.news_item_ids,
        )
        budget = BudgetGuard(BudgetConfig(time_budget_seconds=task_input.time_budget_seconds))
        runtime = self._build_runtime()
        engine = NarrativeLoopEngine(runtime=runtime, session_store=self.session_store, budget=budget)
        return engine.run(session_id=session_id, news_item_ids=task_input.news_item_ids)

    def run_pending(self, limit: int = 20, time_budget_seconds: float = 300.0) -> LoopResult:
        """Pull pending news items from DB and run a harness task over them.

        Phase 1 note: processed items are NOT marked as analyzed in news_items.
        The harness session log is the record of what was processed. Items will
        remain in pending status and will be picked up again on subsequent calls.
        """
        pending_rows = self.repository.list_pending_news(limit=limit)
        news_item_ids = [int(row["id"]) for row in pending_rows]
        return self.run_task(TaskInput(
            news_item_ids=news_item_ids,
            task_description=f"Process {len(news_item_ids)} pending news items",
            time_budget_seconds=time_budget_seconds,
        ))

    def _build_runtime(self) -> ToolRuntime:
        runtime = ToolRuntime(policy_engine=PolicyEngine())
        runtime.register(SortAndAnalyzeTool(self.repository, self._sorter, self._analyst))
        runtime.register(UpdateNarrativeTool(self._narrative_manager, self.storage_root))
        return runtime
