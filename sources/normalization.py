from __future__ import annotations

from typing import Any

from schemas.raw_news_item import RawNewsItem
from utils.clock import now_iso


def build_raw_news_item(
    *,
    source_type: str,
    source_name: str,
    external_id: str | None,
    url: str,
    title: str,
    summary: str | None,
    published_at: str | None,
    extra_payload: dict[str, Any] | None = None,
    fetched_at: str | None = None,
) -> RawNewsItem:
    normalized_summary = (summary or title).strip()
    normalized_fetched_at = fetched_at or now_iso()
    payload = dict(extra_payload or {})
    payload.update(
        {
            "title": title,
            "summary": normalized_summary,
            "source": source_name,
            "url": url,
            "timestamp": published_at or normalized_fetched_at,
            "published_at": published_at,
        }
    )
    payload.update(enrich_payload(title, normalized_summary))
    return RawNewsItem(
        source_type=source_type,
        source_name=source_name,
        external_id=external_id,
        url=url,
        title=title,
        summary=normalized_summary,
        published_at=published_at,
        fetched_at=normalized_fetched_at,
        raw_payload=payload,
    )


def enrich_payload(title: str, summary: str) -> dict[str, object]:
    text = f"{title} {summary}".lower()
    theme = ["macro_regime"]
    region = ["Global"]
    importance_score = 0.62
    structural_score = 0.58
    timeliness_score = 0.75
    verifiability_score = 0.75

    if any(marker in text for marker in ("cpi", "inflation", "pce", "prices")):
        theme = ["inflation"]
        region = ["US"]
        importance_score = 0.82
        structural_score = 0.8
    elif any(marker in text for marker in ("fed", "rates", "yield", "treasury")):
        theme = ["rates"]
        region = ["US"]
        importance_score = 0.8
        structural_score = 0.78
    elif any(marker in text for marker in ("payroll", "labor", "employment", "jobs")):
        theme = ["employment"]
        region = ["US"]
        importance_score = 0.78
        structural_score = 0.74
    elif any(marker in text for marker in ("gdp", "growth", "manufacturing", "pmi")):
        theme = ["growth"]
        importance_score = 0.76
        structural_score = 0.72

    return {
        "region": region,
        "theme": theme,
        "importance_score": importance_score,
        "structural_score": structural_score,
        "timeliness_score": timeliness_score,
        "verifiability_score": verifiability_score,
    }
