from __future__ import annotations

from datetime import datetime, timezone


def _parse(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def session_is_stale(session, all_sessions: list, driver_shifts: list[dict],
                     ttl_hours: float | None = None, now: str | None = None) -> bool:
    """圆桌结论是否可能已过时:
    ① 同资产存在更新的 session;② 该资产有比本 session 更新的驱动切换(局势已变);
    ③ ttl_hours 给定且本 session 超龄。任一为真 → stale。"""
    sct = _parse(session.created_at)
    # ① 同资产更新的 session
    for s in all_sessions:
        if s.asset_id == session.asset_id and s.id != session.id:
            o = _parse(s.created_at)
            if sct is not None and o is not None and o > sct:
                return True
    # ② 同资产更新的驱动切换
    if sct is not None:
        for d in driver_shifts:
            if d.get("node_id") == session.asset_id:
                dt = _parse(d.get("at"))
                if dt is not None and dt > sct:
                    return True
    # ③ TTL 超龄
    if ttl_hours is not None and sct is not None:
        ndt = _parse(now) or datetime.now(timezone.utc)
        if ndt.tzinfo is None:
            ndt = ndt.replace(tzinfo=timezone.utc)
        if sct.tzinfo is None:
            sct = sct.replace(tzinfo=timezone.utc)
        if (ndt - sct).total_seconds() / 3600.0 > ttl_hours:
            return True
    return False
