from __future__ import annotations

from typing import Any

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

    def __init__(self, knowledge_context: dict | None = None) -> None:
        self.knowledge_context = knowledge_context or {}
        self.last_knowledge_docs: dict[str, list[dict]] = {}

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

    def _build_commit_summary(
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
