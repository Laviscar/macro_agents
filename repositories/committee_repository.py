from __future__ import annotations

import json
from pathlib import Path

import yaml

from schemas.committee import (
    CommitteeSeat,
    CommitteeSession,
    CommitteeSkill,
    CommitteeTemplate,
    PendingConvocation,
)


def _safe(name: str) -> str:
    return name.replace("->", "__").replace("/", "_").replace(":", "_").replace(" ", "_")


class CommitteeRepository:
    """文件式存储:待召开 / 圆桌纪要 / 徽章 / 触发状态 + 读写委员会配置。"""

    def __init__(self, storage_root: str | Path, config_dir: str | Path = "config") -> None:
        self.storage_root = Path(storage_root)
        self.config_dir = Path(config_dir)
        self.pending_dir = self.storage_root / "committee_pending"
        self.sessions_dir = self.storage_root / "committee_sessions"
        self.badges_dir = self.storage_root / "committee_badges"
        self.state_path = self.storage_root / "committee_trigger_state.json"
        for d in (self.pending_dir, self.sessions_dir, self.badges_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---- pending ----
    def save_pending(self, p: PendingConvocation) -> None:
        key = _safe(f"{p.asset_id}_{p.trigger}_{p.level if p.level is not None else 'v'}")
        (self.pending_dir / f"{key}.json").write_text(p.model_dump_json(), encoding="utf-8")

    def list_pending(self) -> list[PendingConvocation]:
        items = [PendingConvocation.model_validate_json(f.read_text(encoding="utf-8"))
                 for f in self.pending_dir.glob("*.json")]
        return sorted(items, key=lambda p: p.created_at, reverse=True)  # newest trigger first

    def clear_pending(self, asset_id: str) -> None:
        for f in self.pending_dir.glob("*.json"):
            p = PendingConvocation.model_validate_json(f.read_text(encoding="utf-8"))
            if p.asset_id == asset_id:
                f.unlink()

    def list_active_pending(self) -> list[PendingConvocation]:
        return [p for p in self.list_pending() if p.status == "active"]

    def supersede_pending(self, asset_id: str, keep_created_at: str) -> int:
        """同一资产:把 active 且 created_at < keep_created_at 的旧待召开标记 expired(保留文件)。
        返回被标记的条数。"""
        n = 0
        for f in self.pending_dir.glob("*.json"):
            p = PendingConvocation.model_validate_json(f.read_text(encoding="utf-8"))
            if p.asset_id == asset_id and p.status == "active" and p.created_at < keep_created_at:
                p.status = "expired"
                f.write_text(p.model_dump_json(), encoding="utf-8")
                n += 1
        return n

    # ---- trigger state ----
    def save_trigger_state(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def load_trigger_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    # ---- sessions + badges ----
    def save_session(self, sess: CommitteeSession) -> None:
        (self.sessions_dir / f"{_safe(sess.id)}.json").write_text(sess.model_dump_json(), encoding="utf-8")
        v = sess.verdict
        badge = {"asset": sess.asset_id, "switch_likelihood": v.switch_likelihood,
                 "direction": v.direction, "conviction": v.conviction,
                 "session_id": sess.id, "at": sess.created_at}
        (self.badges_dir / f"{_safe(sess.asset_id)}.json").write_text(
            json.dumps(badge, ensure_ascii=False), encoding="utf-8")

    def list_sessions(self) -> list[CommitteeSession]:
        sessions = [CommitteeSession.model_validate_json(f.read_text(encoding="utf-8"))
                    for f in self.sessions_dir.glob("*.json")]
        return sorted(sessions, key=lambda s: s.created_at, reverse=True)

    def get_badge(self, asset_id: str) -> dict | None:
        path = self.badges_dir / f"{_safe(asset_id)}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def list_badges(self) -> list[dict]:
        return [json.loads(f.read_text(encoding="utf-8")) for f in self.badges_dir.glob("*.json")]

    # ---- config ----
    def _skills_doc(self) -> dict:
        return yaml.safe_load((self.config_dir / "committee_skills.yaml").read_text(encoding="utf-8")) or {}

    def _committee_doc(self) -> dict:
        return yaml.safe_load((self.config_dir / "committee.yaml").read_text(encoding="utf-8")) or {}

    def skill_library(self) -> list[CommitteeSkill]:
        return [CommitteeSkill(**s) for s in self._skills_doc().get("skills", [])]

    def personas(self) -> list[str]:
        return list(self._skills_doc().get("personas", []))

    def default_seats(self) -> list[CommitteeSeat]:
        return [CommitteeSeat(**s) for s in self._committee_doc().get("default_seats", [])]

    def templates(self) -> list[CommitteeTemplate]:
        return [CommitteeTemplate(**t) for t in self._committee_doc().get("templates", [])]

    def default_rounds(self) -> int:
        return int(self._committee_doc().get("default_rounds", 1))

    def default_mode(self) -> str:
        return str(self._committee_doc().get("default_mode", "cross"))

    def save_committee_config(self, seats: list[CommitteeSeat], rounds: int, mode: str) -> None:
        doc = self._committee_doc()
        doc["default_seats"] = [s.model_dump() for s in seats]
        doc["default_rounds"] = int(rounds)
        doc["default_mode"] = mode
        (self.config_dir / "committee.yaml").write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
