from __future__ import annotations

from datetime import datetime, timezone

from utils.clock import now_iso


def _parse(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_min(ts: str | None, now_dt: datetime) -> float | None:
    t = _parse(ts)
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return round((now_dt - t).total_seconds() / 60.0, 1)


def freshness_summary(news_repo, graph_repo, committee_repo, fred_repo=None, now: str | None = None) -> dict:
    """系统各处的"有多新"快照(0 LLM):最新新闻/证据/驱动切换/最老待召开 的年龄 + 积压量。
    供 run_loop 日志与(将来)UI 展示,让用户一眼看清时效。"""
    now = now or now_iso()
    now_dt = _parse(now) or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    rows = news_repo.list_news_items(limit=1)
    latest_news_at = (rows[0].get("published_at") or rows[0].get("fetched_at")) if rows else None
    latest_evidence_at = news_repo.get_latest_analysis_created_at()
    counts = news_repo.get_status_counts()

    shifts = graph_repo.list_driver_shifts()
    latest_shift_at = max((s.get("at", "") for s in shifts), default="") or None

    active = committee_repo.list_active_pending()
    oldest_pending_at = min((p.created_at for p in active), default="") or None

    latest_fred_date = None
    if fred_repo is not None:
        latest_fred_date = max((r.date for r in fred_repo.list_readings()), default="") or None

    return {
        "now": now,
        "latest_news_at": latest_news_at, "latest_news_age_min": _age_min(latest_news_at, now_dt),
        "latest_evidence_at": latest_evidence_at, "latest_evidence_age_min": _age_min(latest_evidence_at, now_dt),
        "latest_shift_at": latest_shift_at, "latest_shift_age_min": _age_min(latest_shift_at, now_dt),
        "oldest_active_pending_at": oldest_pending_at, "oldest_active_pending_age_min": _age_min(oldest_pending_at, now_dt),
        "latest_fred_date": latest_fred_date,
        "pending_sort_backlog": counts.get("pending_sort", 0),
        "pending_analysis_backlog": counts.get("pending_analysis", 0),
        "active_pending_count": len(active),
    }
