from __future__ import annotations

from typing import Any

from schemas.resource_card import ResourceCard
from utils.clock import now_iso
from utils.ids import new_id
from utils.scoring import clamp_score


class NewsSorterAgent:
    """负责原始输入的清洗、评分和路由。"""

    def __init__(self, scoring_rules: dict | None = None) -> None:
        self.scoring_rules = scoring_rules or {}
        self.analysis_threshold = float(self.scoring_rules.get("analysis_threshold", 0.7))
        self.watchlist_threshold = float(self.scoring_rules.get("watchlist_threshold", 0.45))

    def process(self, raw_item: dict[str, Any]) -> ResourceCard:
        timestamp = str(raw_item.get("timestamp") or now_iso())
        title = str(raw_item.get("title") or "").strip()
        summary = str(raw_item.get("summary") or "").strip()
        source = str(raw_item.get("source") or "unknown").strip()
        url = str(raw_item.get("url") or "").strip()
        region = raw_item.get("region") or ["Global"]
        theme = raw_item.get("theme") or ["macro_regime"]
        tags = raw_item.get("tags") or []
        card_type = raw_item.get("card_type") or "news"

        importance_score = clamp_score(raw_item.get("importance_score", 0.5))
        structural_score = clamp_score(raw_item.get("structural_score", 0.5))
        timeliness_score = clamp_score(raw_item.get("timeliness_score", 0.5))
        verifiability_score = clamp_score(raw_item.get("verifiability_score", 0.5))

        analysis_readiness_score = self._score_analysis_readiness(
            importance_score=importance_score,
            structural_score=structural_score,
            verifiability_score=verifiability_score,
        )
        route_decision = self._decide_route(analysis_readiness_score)

        return ResourceCard(
            id=new_id("rc"),
            timestamp=timestamp,
            source=source,
            url=url,
            title=title,
            one_liner=summary or title,
            region=list(region),
            theme=list(theme),
            card_type=card_type,
            tags=list(tags),
            importance_score=importance_score,
            structural_score=structural_score,
            timeliness_score=timeliness_score,
            verifiability_score=verifiability_score,
            analysis_readiness_score=analysis_readiness_score,
            route_to_analysis=route_decision == "send_to_analysis",
            route_decision=route_decision,
            archive_bucket=timestamp[:7].replace("-", "_"),
        )

    def _score_analysis_readiness(
        self,
        importance_score: float,
        structural_score: float,
        verifiability_score: float,
    ) -> float:
        return clamp_score((importance_score + structural_score + verifiability_score) / 3)

    def _decide_route(self, analysis_readiness_score: float) -> str:
        if analysis_readiness_score >= self.analysis_threshold:
            return "send_to_analysis"
        if analysis_readiness_score >= self.watchlist_threshold:
            return "watchlist"
        return "archive_only"
