from __future__ import annotations

import json
from typing import Any

from llm.base import LLMClient, LLMError, LLMMessage
from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence
from schemas.resource_card import ResourceCard
from utils.clock import now_iso
from utils.ids import new_id
from utils.scoring import clamp_score


_VALID_MAINLINE_RELATIONS = {
    "supports", "raises_probability_of", "conflicts_with", "perturbs", "challenges", "unclear",
}
_VALID_SIGNAL_LEVELS = {"fact", "product", "structure", "institution", "theme_candidate"}


class AnalystAgent:
    """负责高信号事件分析与 Evidence 提炼。"""

    def __init__(
        self,
        knowledge_context: dict | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.knowledge_context = knowledge_context or {}
        self.last_knowledge_docs: dict[str, list[dict]] = {}
        self._llm_client = llm_client

    def analyze(
        self,
        resource_card: ResourceCard,
        context: dict[str, Any] | None = None,
    ) -> AnalysisCard:
        context = context or {}
        self._get_task_knowledge("analyze_event")
        if self._llm_client is not None:
            try:
                return self._analyze_with_llm(resource_card, context)
            except (LLMError, ValueError, KeyError, TypeError):
                pass  # fall back to rule-based
        return self._analyze_rule_based(resource_card, context)

    def _analyze_rule_based(
        self,
        resource_card: ResourceCard,
        context: dict[str, Any],
    ) -> AnalysisCard:
        inferred_relation = self._infer_mainline_relation(resource_card)
        mainline_relation = context.get("mainline_relation") or inferred_relation
        candidate_branch_title = context.get("candidate_branch_title")
        confidence = clamp_score(context.get("confidence", 0.6))

        return AnalysisCard(
            id=new_id("ac"),
            event_id=resource_card.id,
            source_card_ids=[resource_card.id],
            reframed_question=self._reframe_question(resource_card),
            signal_level="structure",
            thesis=self._build_thesis(resource_card, mainline_relation),
            evidence_for=[resource_card.one_liner],
            evidence_against=[],
            macro_variables=resource_card.theme,
            asset_mapping=[],
            confidence=confidence,
            mainline_relation=mainline_relation,
            candidate_branch_title=candidate_branch_title,
            invalidation_conditions=[],
            created_at=now_iso(),
        )

    def _analyze_with_llm(
        self,
        resource_card: ResourceCard,
        context: dict[str, Any],
    ) -> AnalysisCard:
        system = (
            "You are a macro analyst. Read the news item and judge its relation to the "
            "current mainline macro narrative. Respond with STRICT JSON only, no prose."
        )
        user = (
            "News item:\n"
            f"- title: {resource_card.title}\n"
            f"- one_liner: {resource_card.one_liner}\n"
            f"- themes: {', '.join(resource_card.theme)}\n\n"
            "Return JSON with keys: mainline_relation (one of "
            "supports|raises_probability_of|conflicts_with|perturbs|challenges|unclear), "
            "thesis (string), confidence (0..1 float), signal_level (one of "
            "fact|product|structure|institution|theme_candidate), reframed_question (string), "
            "evidence_for (string[]), evidence_against (string[]), "
            "invalidation_conditions (string[]), candidate_branch_title (string or null)."
        )
        response = self._llm_client.complete(
            [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
            temperature=0.0,
            max_tokens=700,
        )
        data = json.loads(response.text)  # ValueError on bad JSON → caught by dispatcher

        relation = data["mainline_relation"]
        if relation not in _VALID_MAINLINE_RELATIONS:
            raise ValueError(f"invalid mainline_relation: {relation}")
        signal_level = data.get("signal_level", "structure")
        if signal_level not in _VALID_SIGNAL_LEVELS:
            signal_level = "structure"

        return AnalysisCard(
            id=new_id("ac"),
            event_id=resource_card.id,
            source_card_ids=[resource_card.id],
            reframed_question=data.get("reframed_question") or self._reframe_question(resource_card),
            signal_level=signal_level,
            thesis=data.get("thesis") or self._build_thesis(resource_card, relation),
            evidence_for=list(data.get("evidence_for") or [resource_card.one_liner]),
            evidence_against=list(data.get("evidence_against") or []),
            macro_variables=resource_card.theme,
            asset_mapping=[],
            confidence=clamp_score(float(data.get("confidence", 0.6))),
            mainline_relation=relation,
            candidate_branch_title=data.get("candidate_branch_title"),
            invalidation_conditions=list(data.get("invalidation_conditions") or []),
            created_at=now_iso(),
        )

    def extract_evidence(
        self,
        analysis_card: AnalysisCard,
        context: dict[str, Any] | None = None,
    ) -> list[Evidence]:
        context = context or {}
        self._get_task_knowledge("extract_evidence")
        if self._llm_client is not None:
            try:
                return self._extract_evidence_with_llm(analysis_card, context)
            except (LLMError, ValueError, KeyError, TypeError):
                pass  # fall back to rule-based
        return self._extract_evidence_rule_based(analysis_card, context)

    def _extract_evidence_rule_based(
        self,
        analysis_card: AnalysisCard,
        context: dict[str, Any],
    ) -> list[Evidence]:
        relation_type_map = {
            "supports": "supports",
            "raises_probability_of": "raises_probability_of",
            "conflicts_with": "conflicts_with",
            "perturbs": "complicates",
            "challenges": "conflicts_with",
            "unclear": "complicates",
        }
        target_main_narrative_id = context.get("target_main_narrative_id", "main_default")
        target_branch_id = context.get("target_branch_id")
        claim = self._build_evidence_claim(analysis_card)
        why = self._build_evidence_why(analysis_card)
        counter_evidence = self._build_counter_evidence(analysis_card)

        evidence = Evidence(
            id=new_id("ev"),
            source_analysis_id=analysis_card.id,
            source_card_ids=analysis_card.source_card_ids,
            claim=claim,
            relation_type=relation_type_map[analysis_card.mainline_relation],
            target_main_narrative_id=target_main_narrative_id,
            target_branch_id=target_branch_id,
            strength=clamp_score(context.get("strength", analysis_card.confidence)),
            confidence=analysis_card.confidence,
            why=why,
            counter_evidence=counter_evidence,
            created_at=now_iso(),
        )
        return [evidence]

    def _extract_evidence_with_llm(
        self,
        analysis_card: AnalysisCard,
        context: dict[str, Any],
    ) -> list[Evidence]:
        relation_type_map = {
            "supports": "supports",
            "raises_probability_of": "raises_probability_of",
            "conflicts_with": "conflicts_with",
            "perturbs": "complicates",
            "challenges": "conflicts_with",
            "unclear": "complicates",
        }
        target_main_narrative_id = context.get("target_main_narrative_id", "main_default")
        target_branch_id = context.get("target_branch_id")

        system = (
            "You distill one macro Evidence item from an analysis. Respond with STRICT JSON only."
        )
        user = (
            f"Analysis thesis: {analysis_card.thesis}\n"
            f"Relation to mainline: {analysis_card.mainline_relation}\n"
            f"Supporting points: {', '.join(analysis_card.evidence_for)}\n\n"
            "Return JSON with keys: claim (string, concise), why (string), "
            "counter_evidence (string[]), strength (0..1 float)."
        )
        response = self._llm_client.complete(
            [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
            temperature=0.0,
            max_tokens=400,
        )
        data = json.loads(response.text)

        claim = data.get("claim")
        if not claim:
            raise ValueError("llm evidence missing claim")

        evidence = Evidence(
            id=new_id("ev"),
            source_analysis_id=analysis_card.id,
            source_card_ids=analysis_card.source_card_ids,
            claim=claim,
            relation_type=relation_type_map[analysis_card.mainline_relation],
            target_main_narrative_id=target_main_narrative_id,
            target_branch_id=target_branch_id,
            strength=clamp_score(float(data.get("strength", analysis_card.confidence))),
            confidence=analysis_card.confidence,
            why=data.get("why") or self._build_evidence_why(analysis_card),
            counter_evidence=list(data.get("counter_evidence") or []),
            created_at=now_iso(),
        )
        return [evidence]

    def _reframe_question(self, resource_card: ResourceCard) -> str:
        return f"这条信息是否会改变当前主线叙事的关键命题：{resource_card.title}？"

    def _build_thesis(self, resource_card: ResourceCard, mainline_relation: str) -> str:
        signal = self._extract_signal_phrase(resource_card)

        if mainline_relation == "supports":
            return f"初步判断：{signal}，对当前主线形成直接支持。"
        if mainline_relation == "raises_probability_of":
            return f"初步判断：{signal}，提高了当前主线继续成立的概率。"
        if mainline_relation in {"conflicts_with", "challenges"}:
            return f"初步判断：{signal}，与当前主线存在明显冲突。"

        themes = ", ".join(resource_card.theme)
        return f"初步判断：{signal}，可能扰动 {themes} 相关主线。"

    def _infer_mainline_relation(self, resource_card: ResourceCard) -> str:
        text = f"{resource_card.title} {resource_card.one_liner}".lower()
        themes = {theme.lower() for theme in resource_card.theme}

        easing_markers = ("cool", "slow", "ease", "soft", "declin", "lower than expected")
        heating_markers = ("hotter than expected", "reaccelerat", "surge", "spike", "unexpected rise")
        positive_markers = ("better than expected", "improv", "stabil", "rebound", "resilien")
        negative_markers = ("worse than expected", "weaken", "deteriorat", "contract", "stress")

        if {"inflation", "rates"} & themes:
            if any(marker in text for marker in easing_markers):
                return "supports"
            if any(marker in text for marker in heating_markers):
                return "conflicts_with"

        if {"growth", "employment", "labor", "liquidity"} & themes:
            if any(marker in text for marker in positive_markers):
                return "raises_probability_of"
            if any(marker in text for marker in negative_markers):
                return "conflicts_with"

        if "better than expected" in text:
            return "raises_probability_of"
        if "worse than expected" in text:
            return "conflicts_with"
        return "unclear"

    def _build_evidence_claim(self, analysis_card: AnalysisCard) -> str:
        candidates = [*analysis_card.evidence_for, *analysis_card.evidence_against, analysis_card.thesis]
        for candidate in candidates:
            claim = self._normalize_claim_text(candidate, max_length=48)
            if claim:
                return claim
        return "关键信号变化"

    def _build_evidence_why(self, analysis_card: AnalysisCard) -> str:
        return self._join_evidence_fragments(analysis_card.evidence_for, fallback="直接依据不足")

    def _extract_signal_phrase(self, resource_card: ResourceCard) -> str:
        return self._normalize_claim_text(resource_card.title, max_length=40) or resource_card.title.strip()

    def _normalize_claim_text(self, text: str, max_length: int = 32) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""

        cleaned = cleaned.replace("初步判断：", "").strip()
        for separator in ("。", ".", "；", ";", "，", ",", "：", ":"):
            if separator in cleaned:
                cleaned = cleaned.split(separator, 1)[0].strip()
                break

        cleaned = cleaned.rstrip("。.;；,，:：")
        if len(cleaned) <= max_length:
            return cleaned

        natural_cut = self._find_natural_cut(cleaned, max_length)
        if natural_cut is not None:
            return cleaned[:natural_cut].rstrip("。.;；,，:： ")

        return cleaned[:max_length].rstrip("。.;；,，:： ")

    def _find_natural_cut(self, text: str, max_length: int) -> int | None:
        boundary_chars = {" ", "/", "-", "(", ")", "[", "]"}
        punctuation_chars = {"。", ".", "；", ";", "，", ",", "：", ":", "！", "!", "？", "?"}

        candidates: list[int] = []
        upper_bound = min(len(text), max_length + 1)

        for index, char in enumerate(text[:upper_bound]):
            if index == 0:
                continue
            if char in boundary_chars or char in punctuation_chars:
                candidates.append(index)

        if candidates:
            return max(candidates)

        # Avoid chopping the middle of an ASCII word like "month" -> "mo".
        if max_length < len(text) and text[max_length - 1].isascii() and text[max_length].isascii():
            for index in range(max_length - 1, 0, -1):
                if text[index] in boundary_chars or text[index] in punctuation_chars:
                    return index

        return None

    def _join_evidence_fragments(self, items: list[str], fallback: str) -> str:
        normalized = [self._clean_explanation_text(item) for item in items if self._clean_explanation_text(item)]
        if not normalized:
            return fallback
        return "；".join(normalized)

    def _clean_explanation_text(self, text: str) -> str:
        return text.strip().rstrip("。.;；,，:： ")

    def _build_counter_evidence(self, analysis_card: AnalysisCard) -> list[str]:
        return [self._clean_explanation_text(item) for item in analysis_card.evidence_against if self._clean_explanation_text(item)]

    def _get_task_knowledge(self, task: str) -> list[dict]:
        always_docs = list(self.knowledge_context.get("always", []))
        task_docs = list(self.knowledge_context.get("tasks", {}).get(task, []))
        docs = [*always_docs, *task_docs]
        self.last_knowledge_docs[task] = docs
        return docs
