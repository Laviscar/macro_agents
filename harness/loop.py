from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from harness.budget import BudgetGuard
from harness.events import EventType, LoopEvent
from harness.policy import PolicyDecision
from harness.runtime import ToolResult, ToolRuntime
from harness.session_store import HarnessSessionStore
from llm.metering import TokenMeter
from schemas.evidence import Evidence


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
    planned_tools: list[str] = field(default_factory=list)
    all_skipped: bool = False  # set by OBSERVE handler; prevents UPDATE_NARRATIVE when no evidence


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
        token_meter: "TokenMeter | None" = None,
    ) -> None:
        self.runtime = runtime
        self.session_store = session_store
        self.budget = budget
        self._token_meter = token_meter
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
        result_payload: dict = {"stop_reason": ctx.stop_reason}
        if ctx.narrative_result:
            result_payload.update(ctx.narrative_result)
        self._emit(ctx, EventType.SESSION_COMPLETED, result_payload)
        self.session_store.complete_session(session_id, result_payload)
        return LoopResult(
            session_id=session_id,
            final_state=LoopState.DONE,
            narrative_result=ctx.narrative_result,
            stop_reason=ctx.stop_reason,
            events_count=self._events_count,
        )

    def _handle(self, ctx: LoopContext) -> None:
        if ctx.current_state == LoopState.PLAN:
            ctx.planned_tools = ["sort_and_analyze"] if ctx.news_item_ids else []
            self._emit(ctx, EventType.PLAN_DECIDED, {
                "planned_tools": ctx.planned_tools,
                "news_item_count": len(ctx.news_item_ids),
            })

        elif ctx.current_state == LoopState.TOOL_EXEC:
            if not ctx.planned_tools:
                return  # PLAN decided nothing to do

            for tool_name in ctx.planned_tools:
                self._emit(ctx, EventType.TOOL_CALL, {
                    "tool": tool_name,
                    "news_item_ids": ctx.news_item_ids,
                })
                result = self.runtime.execute(tool_name, {"news_item_ids": ctx.news_item_ids})
                ctx.tool_results.append(result)
                intercepted = (
                    result.policy_record is not None
                    and result.policy_record.decision != PolicyDecision.ALLOW
                )
                self._emit(ctx, EventType.TOOL_RESULT, {
                    "tool": tool_name,
                    "success": result.success,
                    "error": result.error,
                    "processed": result.output.get("processed", 0) if result.success and result.output else 0,
                    "policy_intercepted": intercepted,
                })
                if result.policy_record is not None:
                    self._emit(ctx, EventType.POLICY_DECISION, {
                        "tool": result.policy_record.tool_name,
                        "risk_level": result.policy_record.risk_level,
                        "decision": result.policy_record.decision,
                        "reason": result.policy_record.reason,
                    })
                if not result.success:
                    raise RuntimeError(f"{tool_name} failed: {result.error}")

        elif ctx.current_state == LoopState.OBSERVE:
            all_evidence: list[Evidence] = []
            total_processed = 0
            for r in ctx.tool_results:
                if r.success and r.output:
                    all_evidence.extend(r.output.get("evidence_list", []))
                    total_processed += r.output.get("processed", 0)

            if total_processed > 0 and len(all_evidence) == 0:
                ctx.all_skipped = True

            avg_confidence = (
                sum(e.confidence for e in all_evidence) / len(all_evidence)
                if all_evidence else 1.0
            )

            self._emit(ctx, EventType.OBSERVE_RESULT, {
                "evidence_count": len(all_evidence),
                "all_skipped": ctx.all_skipped,
                "avg_confidence": round(avg_confidence, 3),
            })

        elif ctx.current_state == LoopState.UPDATE_NARRATIVE:
            if not ctx.tool_results or ctx.all_skipped:
                self._emit(ctx, EventType.TOOL_RESULT, {
                    "tool": "update_narrative",
                    "skipped": True,
                    "reason": "no_evidence" if ctx.all_skipped else "no_tools_ran",
                })
                return

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
            if result.policy_record is not None:
                self._emit(ctx, EventType.POLICY_DECISION, {
                    "tool": result.policy_record.tool_name,
                    "risk_level": result.policy_record.risk_level,
                    "decision": result.policy_record.decision,
                    "reason": result.policy_record.reason,
                })
            if not result.success:
                raise RuntimeError(f"update_narrative failed: {result.error}")

        elif ctx.current_state == LoopState.CHECK_BUDGET_AND_STOP:
            if self._token_meter is not None:
                self.budget.add_tokens(self._token_meter.drain())
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
