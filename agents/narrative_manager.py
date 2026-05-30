from __future__ import annotations

import json
from typing import Any

from llm.base import LLMClient, LLMError, LLMMessage
from schemas.analysis_card import AnalysisCard
from schemas.branch_narrative import BranchNarrative
from schemas.challenge_alert import ChallengeAlert
from schemas.evidence import Evidence
from schemas.main_narrative import MainNarrative
from schemas.narrative_commit import NarrativeCommit
from schemas.scenario_split import ScenarioSplit
from utils.clock import now_iso
from utils.ids import new_id
from utils.scoring import clamp_score


class NarrativeManagerAgent:
    """
    使用 Evidence 作为叙事状态更新的唯一触发器。

    AnalysisCard 只用于辅助命名、审计和补充上下文。
    """

    def __init__(
        self,
        knowledge_context: dict | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.knowledge_context = knowledge_context or {}
        self.last_knowledge_docs: dict[str, list[dict]] = {}
        self._llm_client = llm_client

    def update(
        self,
        evidence_list: list[Evidence],
        analysis_card: AnalysisCard | None = None,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._get_task_knowledge("record_commit")
        current_state = self._ensure_state(state)

        if not evidence_list:
            return current_state

        main_narrative: MainNarrative = current_state["main_narrative"]
        # Seed a real thesis on a still-placeholder narrative BEFORE building any commit/
        # alert, so even a first-batch challenge alert references a meaningful claim
        # (not "待定义"). Fires at most once (guarded on the placeholder); LLM with fallback.
        if self._llm_client is not None and (
            not main_narrative.core_claims or main_narrative.core_claims == ["待定义"]
        ):
            try:
                thesis = self._read_line_with_llm(main_narrative, evidence_list)
                main_narrative = main_narrative.model_copy(update={"core_claims": [thesis]})
                current_state["main_narrative"] = main_narrative
            except (LLMError, ValueError, KeyError, TypeError):
                pass
        branches: list[BranchNarrative] = list(current_state["branches"])
        commits: list[NarrativeCommit] = list(current_state["commits"])
        alerts: list[ChallengeAlert] = list(current_state["alerts"])
        scenarios: list[ScenarioSplit] = list(current_state["scenarios"])

        source_evidence_ids = [evidence.id for evidence in evidence_list]
        evidence_claims = [evidence.claim for evidence in evidence_list]
        relation_summary = self._summarize_relations(evidence_list)
        avg_strength = relation_summary["avg_strength"]
        avg_confidence = relation_summary["avg_confidence"]
        challenge_probability = relation_summary["challenge_probability"]
        branch_mode = relation_summary["branch_mode"]

        if self._llm_client is not None:
            try:
                challenge_probability, branch_mode = self._judge_challenge_with_llm(
                    evidence_list, main_narrative
                )
            except (LLMError, ValueError, KeyError, TypeError):
                pass  # fall back to rule-derived values

        updated_main = main_narrative.model_copy(
            update={
                "supporting_evidence": [
                    *main_narrative.supporting_evidence,
                    *relation_summary["main_supporting_evidence"],
                ],
                "counter_evidence": [
                    *main_narrative.counter_evidence,
                    *relation_summary["main_counter_evidence"],
                ],
                "strength": self._apply_directional_delta(
                    main_narrative.strength,
                    relation_summary["main_strength_delta"],
                ),
                "confidence": self._apply_directional_delta(
                    main_narrative.confidence,
                    relation_summary["main_confidence_delta"],
                ),
                "fragility": [
                    *main_narrative.fragility,
                    *relation_summary["fragility_items"],
                ],
                "watch_items": [
                    *main_narrative.watch_items,
                    *relation_summary["watch_items"],
                ],
                "updated_at": now_iso(),
            }
        )
        new_branch = None
        if branch_mode:
            branch_title = self._build_branch_title(analysis_card, evidence_list)
            branch_core_claim = (
                analysis_card.thesis
                if analysis_card
                else evidence_claims[0]
            )
            new_branch = BranchNarrative(
                id=new_id("branch"),
                parent_main_narrative_id=updated_main.id,
                title=branch_title,
                region=updated_main.region,
                theme=updated_main.theme,
                status=self._branch_status_for_probability(challenge_probability),
                core_claims=[branch_core_claim],
                supporting_evidence=relation_summary["branch_supporting_evidence"],
                counter_evidence=relation_summary["branch_counter_evidence"],
                branch_strength=relation_summary["branch_strength"],
                challenge_probability=challenge_probability,
                market_priced=clamp_score(challenge_probability / 2),
                fragility=[
                    *(analysis_card.invalidation_conditions if analysis_card else []),
                    *relation_summary["fragility_items"],
                ],
                key_triggers=relation_summary["watch_items"],
                created_at=now_iso(),
                updated_at=now_iso(),
            )

        commit_target = self._select_commit_target(
            relation_summary["dominant_relation"],
            updated_main,
            new_branch,
        )
        commit = NarrativeCommit(
            id=new_id("commit"),
            narrative_type=commit_target["narrative_type"],
            narrative_id=commit_target["narrative_id"],
            source_evidence_ids=source_evidence_ids,
            action="update",
            summary=self._build_commit_summary(
                relation_summary["dominant_relation"],
                updated_main,
                new_branch,
                evidence_list,
            ),
            field_changes=self._build_field_changes(
                relation_summary["dominant_relation"],
                main_narrative,
                updated_main,
                new_branch,
            ),
            created_at=now_iso(),
        )

        alert = None
        if branch_mode and new_branch and challenge_probability >= 0.65:
            alert = ChallengeAlert(
                id=new_id("alert"),
                main_narrative_id=updated_main.id,
                branch_narrative_id=new_branch.id,
                challenged_claim=updated_main.core_claims[0],
                challenge_probability=challenge_probability,
                key_triggers=[],
                sensitive_assets=[],
                scenario_a_main_holds=[],
                scenario_b_branch_takes_over=[],
                created_at=now_iso(),
            )

        scenario = None
        if branch_mode and new_branch:
            scenario = ScenarioSplit(
                id=new_id("scenario"),
                main_narrative_id=updated_main.id,
                branch_narrative_id=new_branch.id,
                scenario_a_name="主线延续",
                scenario_a_implications=[],
                scenario_b_name="分支上位",
                scenario_b_implications=[],
                probability_split={
                    "scenario_a": clamp_score(1 - challenge_probability),
                    "scenario_b": challenge_probability,
                },
                updated_at=now_iso(),
            )

        if new_branch:
            branches.append(new_branch)
        commits.append(commit)
        if alert:
            alerts.append(alert)
        if scenario:
            scenarios.append(scenario)

        return {
            "main_narrative": updated_main,
            "branches": branches,
            "commits": commits,
            "alerts": alerts,
            "scenarios": scenarios,
        }

    def _ensure_state(self, state: dict[str, Any] | None) -> dict[str, Any]:
        current_state = dict(state or {})
        if "main_narrative" not in current_state:
            current_state["main_narrative"] = self._default_main_narrative()
        current_state.setdefault("branches", [])
        current_state.setdefault("commits", [])
        current_state.setdefault("alerts", [])
        current_state.setdefault("scenarios", [])
        return current_state

    def _default_main_narrative(self) -> MainNarrative:
        timestamp = now_iso()
        return MainNarrative(
            id="main_default",
            title="默认主线",
            region="Global",
            theme="macro_regime",
            status="active",
            version=1,
            core_claims=["待定义"],
            supporting_evidence=[],
            counter_evidence=[],
            strength=0.5,
            confidence=0.5,
            market_consensus=0.5,
            market_priced=0.5,
            fragility=[],
            watch_items=[],
            replaced_by=None,
            effective_from=timestamp,
            updated_at=timestamp,
        )

    def _build_branch_title(
        self,
        analysis_card: AnalysisCard | None,
        evidence_list: list[Evidence],
    ) -> str:
        if analysis_card and analysis_card.candidate_branch_title:
            return analysis_card.candidate_branch_title
        # Fall back to the (LLM-generated) driving evidence claim instead of an opaque
        # "Branch from rc_xxx" id. Reuses an existing claim — no extra LLM call.
        claim = self._representative_claim(evidence_list)
        if claim:
            return claim if len(claim) <= 48 else claim[:48].rstrip() + "…"
        if analysis_card:
            return f"Branch from {analysis_card.event_id}"
        return f"Branch from {evidence_list[0].id}"

    def _derive_challenge_probability(self, evidence_list: list[Evidence]) -> float:
        if not evidence_list:
            return 0.0

        weights = {
            "supports": 0.15,
            "complicates": 0.4,
            "lowers_probability_of": 0.55,
            "raises_probability_of": 0.25,
            "conflicts_with": 0.7,
        }

        scores = [
            clamp_score(((evidence.strength + evidence.confidence) / 2 + weights[evidence.relation_type]) / 2)
            for evidence in evidence_list
        ]
        return clamp_score(sum(scores) / len(scores))

    def _branch_status_for_probability(self, challenge_probability: float) -> str:
        if challenge_probability >= 0.65:
            return "challenger"
        if challenge_probability >= 0.5:
            return "strengthening"
        if challenge_probability >= 0.3:
            return "watching"
        return "seed"

    def _get_task_knowledge(self, task: str) -> list[dict]:
        always_docs = list(self.knowledge_context.get("always", []))
        task_docs = list(self.knowledge_context.get("tasks", {}).get(task, []))
        docs = [*always_docs, *task_docs]
        self.last_knowledge_docs[task] = docs
        return docs

    def _judge_challenge_with_llm(
        self,
        evidence_list: list[Evidence],
        main_narrative: MainNarrative,
    ) -> tuple[float, bool]:
        system = (
            "You are a macro narrative risk judge. Decide whether incoming evidence warrants "
            "opening a CHALLENGE branch against the mainline narrative, and estimate the "
            "challenge probability. Respond with STRICT JSON only, no prose."
        )
        ev_lines = "\n".join(
            f"- [{e.relation_type}] {e.claim} (strength={e.strength:.2f}, confidence={e.confidence:.2f})"
            for e in evidence_list
        )
        user = (
            f"Mainline narrative: {main_narrative.title}\n"
            f"Core claims: {', '.join(main_narrative.core_claims)}\n"
            f"Current strength={main_narrative.strength:.2f}, confidence={main_narrative.confidence:.2f}\n\n"
            f"New evidence:\n{ev_lines}\n\n"
            "Return JSON with keys: challenge_probability (0..1 float), "
            "open_branch (boolean), reason (string)."
        )
        response = self._llm_client.complete(
            [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
            temperature=0.0,
            max_tokens=4096,  # generous cap so reasoning models can finish (only an upper bound)
        )
        data = json.loads(response.text)
        open_branch = data["open_branch"]
        if not isinstance(open_branch, bool):
            raise ValueError("open_branch must be a boolean")
        challenge_probability = clamp_score(float(data["challenge_probability"]))
        return challenge_probability, open_branch

    def generate_read_line(
        self,
        main_narrative: MainNarrative,
        evidence_list: list[Evidence],
    ) -> str:
        """One-sentence 'current read' of the narrative for the briefing page.

        LLM-generated when a client is present; falls back to a templated line.
        """
        if self._llm_client is not None:
            try:
                return self._read_line_with_llm(main_narrative, evidence_list)
            except (LLMError, ValueError, KeyError, TypeError):
                pass
        return self._read_line_rule_based(main_narrative)

    def _read_line_with_llm(
        self,
        main_narrative: MainNarrative,
        evidence_list: list[Evidence],
    ) -> str:
        ev = "\n".join(f"- [{e.relation_type}] {e.claim}" for e in evidence_list[:8])
        system = (
            "You write a single-sentence macro 'narrative read' for a research dashboard. "
            "Output ONE sentence in Chinese, no quotes, no prose around it."
        )
        user = (
            f"Mainline narrative: {main_narrative.title}\n"
            f"Strength={main_narrative.strength:.2f}, Confidence={main_narrative.confidence:.2f}\n"
            f"Recent evidence:\n{ev or '(none)'}\n\n"
            "Write ONE Chinese sentence: what the current read of this narrative is, "
            "plus the main tension/risk to watch."
        )
        response = self._llm_client.complete(
            [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
            temperature=0.0,
            max_tokens=4096,  # generous cap so reasoning models can finish
        )
        line = response.text.strip().strip('"').strip()
        if not line:
            raise ValueError("empty read line")
        return line

    def _read_line_rule_based(self, main_narrative: MainNarrative) -> str:
        watch = main_narrative.watch_items[:2]
        if watch:
            return f"主线「{main_narrative.title}」延续中,需关注:{'、'.join(watch)}。"
        if main_narrative.fragility:
            return f"主线「{main_narrative.title}」延续,但存在脆弱点:{main_narrative.fragility[0]}。"
        return f"主线「{main_narrative.title}」当前相对稳固。"

    def _summarize_relations(self, evidence_list: list[Evidence]) -> dict[str, Any]:
        avg_strength = clamp_score(
            sum(evidence.strength for evidence in evidence_list) / len(evidence_list)
        )
        avg_confidence = clamp_score(
            sum(evidence.confidence for evidence in evidence_list) / len(evidence_list)
        )
        relation_counts: dict[str, int] = {}
        main_supporting_evidence: list[str] = []
        main_counter_evidence: list[str] = []
        branch_supporting_evidence: list[str] = []
        branch_counter_evidence: list[str] = []
        fragility_items: list[str] = []
        watch_items: list[str] = []
        main_strength_delta = 0.0
        main_confidence_delta = 0.0
        branch_strength = 0.1

        for evidence in evidence_list:
            relation = evidence.relation_type
            relation_counts[relation] = relation_counts.get(relation, 0) + 1

            if relation == "supports":
                main_supporting_evidence.append(evidence.id)
                main_strength_delta += 0.12 * evidence.strength
                main_confidence_delta += 0.08 * evidence.confidence
                continue

            if relation == "raises_probability_of":
                main_supporting_evidence.append(evidence.id)
                main_strength_delta += 0.08 * evidence.strength
                main_confidence_delta += 0.06 * evidence.confidence
                watch_items.append(evidence.claim)
                continue

            if relation == "conflicts_with":
                main_counter_evidence.append(evidence.id)
                branch_supporting_evidence.append(evidence.id)
                fragility_items.append(evidence.claim)
                main_strength_delta -= 0.12 * evidence.strength
                main_confidence_delta -= 0.08 * evidence.confidence
                branch_strength = max(branch_strength, clamp_score(0.6 * evidence.strength))
                continue

            if relation == "lowers_probability_of":
                main_counter_evidence.append(evidence.id)
                branch_supporting_evidence.append(evidence.id)
                watch_items.append(evidence.claim)
                main_strength_delta -= 0.08 * evidence.strength
                main_confidence_delta -= 0.06 * evidence.confidence
                branch_strength = max(branch_strength, clamp_score(0.45 * evidence.strength))
                continue

            fragility_items.append(evidence.claim)
            watch_items.append(evidence.claim)
            branch_strength = max(branch_strength, clamp_score(0.25 * evidence.strength))

        dominant_relation = max(
            relation_counts.items(),
            key=lambda item: (item[1], self._relation_priority(item[0])),
        )[0]

        return {
            "avg_strength": avg_strength,
            "avg_confidence": avg_confidence,
            "challenge_probability": self._derive_challenge_probability(evidence_list),
            "dominant_relation": dominant_relation,
            "branch_mode": dominant_relation in {"conflicts_with", "lowers_probability_of"},
            "main_supporting_evidence": main_supporting_evidence,
            "main_counter_evidence": main_counter_evidence,
            "branch_supporting_evidence": branch_supporting_evidence,
            "branch_counter_evidence": branch_counter_evidence,
            "fragility_items": fragility_items,
            "watch_items": watch_items,
            "main_strength_delta": main_strength_delta,
            "main_confidence_delta": main_confidence_delta,
            "branch_strength": branch_strength,
        }

    def _apply_directional_delta(self, base: float, delta: float) -> float:
        return clamp_score(base + delta)

    def _relation_priority(self, relation_type: str) -> int:
        priorities = {
            "conflicts_with": 5,
            "lowers_probability_of": 4,
            "complicates": 3,
            "raises_probability_of": 2,
            "supports": 1,
        }
        return priorities.get(relation_type, 0)

    def _select_commit_target(
        self,
        dominant_relation: str,
        updated_main: MainNarrative,
        new_branch: BranchNarrative | None,
    ) -> dict[str, str]:
        if dominant_relation in {"conflicts_with", "lowers_probability_of"} and new_branch is not None:
            return {"narrative_type": "branch", "narrative_id": new_branch.id}
        return {"narrative_type": "main", "narrative_id": updated_main.id}

    _COMMIT_DIRECTION_TAG = {
        "supports": "强化主线",
        "raises_probability_of": "提高主线概率",
        "conflicts_with": "与主线冲突",
        "lowers_probability_of": "下修主线概率",
        "complicates": "增加脆弱点/观察项",
    }

    def _build_commit_summary(
        self,
        dominant_relation: str,
        updated_main: MainNarrative,
        new_branch: BranchNarrative | None,
        evidence_list: list[Evidence],
    ) -> str:
        """Prefer the (LLM-generated) representative evidence claim + a direction tag;
        fall back to the rule template only when no claim text is available."""
        claim = self._representative_claim(evidence_list)
        if not claim:
            return self._build_commit_summary_template(dominant_relation, updated_main, new_branch)
        tag = self._COMMIT_DIRECTION_TAG.get(dominant_relation, "更新主线")
        if new_branch is not None and dominant_relation in {"conflicts_with", "lowers_probability_of"}:
            tag = "强化挑战分支"
        return f"{claim}（{tag}）"

    def _representative_claim(self, evidence_list: list[Evidence]) -> str:
        if not evidence_list:
            return ""
        strongest = max(evidence_list, key=lambda evidence: evidence.strength)
        return strongest.claim.strip()

    def _build_commit_summary_template(
        self,
        dominant_relation: str,
        updated_main: MainNarrative,
        new_branch: BranchNarrative | None,
    ) -> str:
        if dominant_relation == "supports":
            return f"{updated_main.title} 因 supports evidence 被强化"
        if dominant_relation == "raises_probability_of":
            return f"{updated_main.title} 因概率上行 evidence 被小幅强化"
        if dominant_relation == "conflicts_with" and new_branch is not None:
            return f"{new_branch.title} 因冲突 evidence 被强化为挑战分支"
        if dominant_relation == "lowers_probability_of" and new_branch is not None:
            return f"{new_branch.title} 因概率下修 evidence 被提升关注"
        return f"{updated_main.title} 因复杂 evidence 增加了脆弱点与观察项"

    def _build_field_changes(
        self,
        dominant_relation: str,
        original_main: MainNarrative,
        updated_main: MainNarrative,
        new_branch: BranchNarrative | None,
    ) -> dict[str, Any]:
        if dominant_relation in {"supports", "raises_probability_of", "complicates"}:
            changes: dict[str, Any] = {
                "strength": {"from": original_main.strength, "to": updated_main.strength},
                "confidence": {"from": original_main.confidence, "to": updated_main.confidence},
            }
            if dominant_relation == "complicates":
                changes["fragility_count"] = {
                    "from": len(original_main.fragility),
                    "to": len(updated_main.fragility),
                }
                changes["watch_items_count"] = {
                    "from": len(original_main.watch_items),
                    "to": len(updated_main.watch_items),
                }
            return changes

        if new_branch is None:
            return {
                "strength": {"from": original_main.strength, "to": updated_main.strength},
                "confidence": {"from": original_main.confidence, "to": updated_main.confidence},
            }

        return {
            "branch_strength": {"from": 0.0, "to": new_branch.branch_strength},
            "challenge_probability": {"from": 0.0, "to": new_branch.challenge_probability},
        }
