from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from harness.budget import BudgetGuard
from harness.events import EventType, LoopEvent
from harness.runtime import ToolResult, ToolRuntime
from harness.session_store import HarnessSessionStore


class LoopState(str, Enum):
    INIT = "INIT"
    PLAN = "PLAN"
    TOOL_EXEC = "TOOL_EXEC"
    OBSERVE = "OBSERVE"
    UPDATE_NARRATIVE = "UPDATE_NARRATIVE"
    CHECK_BUDGET_AND_STOP = "CHECK_BUDGET_AND_STOP"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class LoopContext:
    session_id: str
    news_item_ids: list[int]
    current_state: LoopState = LoopState.INIT
    tool_results: list[ToolResult] = field(default_factory=list)
    narrative_result: dict | None = None
    stop_reason: str | None = None


@dataclass
class LoopResult:
    session_id: str
    final_state: LoopState
    narrative_result: dict | None
    stop_reason: str | None
    events_count: int


_PHASE1_STEPS = [
    LoopState.PLAN,
    LoopState.TOOL_EXEC,
    LoopState.OBSERVE,
    LoopState.UPDATE_NARRATIVE,
    LoopState.CHECK_BUDGET_AND_STOP,
]


class NarrativeLoopEngine:
    def __init__(
        self,
        runtime: ToolRuntime,
        session_store: HarnessSessionStore,
        budget: BudgetGuard,
    ) -> None:
        self.runtime = runtime
        self.session_store = session_store
        self.budget = budget
        self._events_count = 0

    def run(self, session_id: str, news_item_ids: list[int]) -> LoopResult:
        self._events_count = 0
        ctx = LoopContext(session_id=session_id, news_item_ids=news_item_ids)
        self._emit(ctx, EventType.SESSION_STARTED, {})

        try:
            for state in _PHASE1_STEPS:
                prev = ctx.current_state
                ctx.current_state = state
                self._emit(ctx, EventType.LOOP_TRANSITION, {"from": prev, "to": state})
                self._handle(ctx)
        except Exception as exc:
            failed_in_state = ctx.current_state  # capture which state raised
            ctx.current_state = LoopState.FAILED
            ctx.stop_reason = str(exc)
            self._emit(ctx, EventType.LOOP_TRANSITION, {
                "from": failed_in_state,
                "to": LoopState.FAILED,
                "error": str(exc),
            })
            self.session_store.fail_session(session_id, str(exc))
            return LoopResult(
                session_id=session_id,
                final_state=LoopState.FAILED,
                narrative_result=None,
                stop_reason=str(exc),
                events_count=self._events_count,
            )

        ctx.current_state = LoopState.DONE
        self._emit(ctx, EventType.SESSION_COMPLETED, {"stop_reason": ctx.stop_reason})
        self.session_store.complete_session(session_id, {"stop_reason": ctx.stop_reason})
        return LoopResult(
            session_id=session_id,
            final_state=LoopState.DONE,
            narrative_result=ctx.narrative_result,
            stop_reason=ctx.stop_reason,
            events_count=self._events_count,
        )

    def _handle(self, ctx: LoopContext) -> None:
        if ctx.current_state == LoopState.PLAN:
            pass  # Phase 1: static plan, no LLM needed

        elif ctx.current_state == LoopState.TOOL_EXEC:
            self._emit(ctx, EventType.TOOL_CALL, {
                "tool": "sort_and_analyze",
                "news_item_ids": ctx.news_item_ids,
            })
            result = self.runtime.execute("sort_and_analyze", {"news_item_ids": ctx.news_item_ids})
            ctx.tool_results.append(result)
            self._emit(ctx, EventType.TOOL_RESULT, {
                "tool": "sort_and_analyze",
                "success": result.success,
                "error": result.error,
                "processed": result.output.get("processed", 0) if result.success and result.output else 0,
            })
            if not result.success:
                raise RuntimeError(f"sort_and_analyze failed: {result.error}")

        elif ctx.current_state == LoopState.OBSERVE:
            pass  # Phase 1: tool results already verified in TOOL_EXEC

        elif ctx.current_state == LoopState.UPDATE_NARRATIVE:
            all_evidence = []
            all_analysis_cards = []
            for r in ctx.tool_results:
                if r.success and r.output:
                    all_evidence.extend(r.output.get("evidence_list", []))
                    all_analysis_cards.extend(r.output.get("analysis_cards", []))
            self._emit(ctx, EventType.TOOL_CALL, {
                "tool": "update_narrative",
                "evidence_count": len(all_evidence),
                "analysis_card_count": len(all_analysis_cards),
            })
            result = self.runtime.execute("update_narrative", {
                "evidence_list": all_evidence,
                "analysis_cards": all_analysis_cards,
            })
            ctx.narrative_result = result.output
            self._emit(ctx, EventType.TOOL_RESULT, {
                "tool": "update_narrative",
                "success": result.success,
                "error": result.error,
            })
            if not result.success:
                raise RuntimeError(f"update_narrative failed: {result.error}")

        elif ctx.current_state == LoopState.CHECK_BUDGET_AND_STOP:
            status = self.budget.check()
            self._emit(ctx, EventType.BUDGET_CHECK, {
                "ok": status.ok,
                "reason": status.reason,
                "elapsed_seconds": round(status.elapsed_seconds, 3),
                "tokens_used": status.tokens_used,
            })
            ctx.stop_reason = "task_complete" if status.ok else status.reason

    def _emit(self, ctx: LoopContext, event_type: EventType, payload: dict) -> None:
        self._events_count += 1
        event = LoopEvent(
            session_id=ctx.session_id,
            event_type=event_type,
            state=ctx.current_state,
            payload=payload,
        )
        self.session_store.record_event(event)
