from __future__ import annotations

import json
import re

from llm.base import LLMClient, LLMError, LLMMessage
from schemas.committee import CommitteeSeat, CommitteeSession, CommitteeVerdict, PendingConvocation, SeatRemark
from utils.clock import now_iso
from utils.logger import get_logger

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_json(text: str) -> dict:
    return json.loads(_FENCE.sub("", text).strip())


class SeatRunner:
    """一位委员:按 persona + expertise + 勾选 skills 的描述,对上下文给出批判。"""

    def __init__(self, seat: CommitteeSeat, client: LLMClient, skill_desc: dict[str, str], logger=None) -> None:
        self.seat = seat
        self.client = client
        self.skill_desc = skill_desc
        self._logger = logger or get_logger("macro_agents.committee")

    def _system(self) -> str:
        skills = "；".join(f"{sid}({self.skill_desc.get(sid, '')})" for sid in self.seat.skills) or "（无特定专长）"
        return (
            f"你是宏观叙事委员会的一位委员,人格立场:{self.seat.persona}。"
            f"专长:{', '.join(self.seat.expertise) or '综合'}。分析视角(skills):{skills}。"
            "请从你的人格与视角出发,批判性评估这次驱动切换是真信号还是噪音、对多空的影响。简洁有据,中文。"
        )

    def critique(self, context: str, peers: list[str] | None, round_no: int) -> SeatRemark | None:
        peer_block = ""
        if peers:
            peer_block = "\n\n其他委员上轮观点:\n" + "\n".join(f"- {p}" for p in peers)
        user = f"{context}{peer_block}"
        try:
            resp = self.client.complete(
                [LLMMessage(role="system", content=self._system()), LLMMessage(role="user", content=user)],
                temperature=0.0, max_tokens=4096,
            )
        except LLMError as exc:
            self._logger.warning("committee seat %s failed: %s", self.seat.name, exc)
            return None
        return SeatRemark(seat_name=self.seat.name, persona=self.seat.persona, round=round_no, critique=resp.text.strip())


_CHAIR_SYSTEM = (
    "你是宏观叙事委员会主席。综合各委员发言,产出一份机构投委会备忘录级结论。严格只输出 JSON,字段:"
    '{"bottom_line": str(BLUF一段话核心判断), "whats_changing": str, '
    '"switch_likelihood": "将至"|"不确定"|"噪音", "direction": "偏多"|"偏空"|"中性", '
    '"conviction": "高"|"中"|"低", "confidence": 0..1 float, "time_horizon": str, '
    '"catalysts_to_watch": [str], "invalidation": str(什么会证伪/止损逻辑), "positioning": str, '
    '"key_disagreements": [str](委员间分歧), "evidence_basis": [str](支撑论点的证据)}'
)


class ChairSynthesizer:
    def __init__(self, client: LLMClient, logger=None) -> None:
        self.client = client
        self._logger = logger or get_logger("macro_agents.committee")

    def synthesize(self, context: str, remarks_text: str) -> CommitteeVerdict:
        user = f"背景:\n{context}\n\n委员发言:\n{remarks_text}\n\n请综合成备忘录 JSON。"
        try:
            resp = self.client.complete(
                [LLMMessage(role="system", content=_CHAIR_SYSTEM), LLMMessage(role="user", content=user)],
                temperature=0.0, max_tokens=4096,
            )
            return CommitteeVerdict(**_parse_json(resp.text))
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            self._logger.warning("committee chair synthesis failed: %s", exc)
            return CommitteeVerdict(
                bottom_line="(主席综合失败,无法得出结论)", whats_changing="", switch_likelihood="不确定",
                direction="中性", conviction="低", confidence=0.0, time_horizon="—", catalysts_to_watch=[],
                invalidation="—", positioning="—", key_disagreements=[], evidence_basis=[])


class NarrativeCommittee:
    """编排一场圆桌:多轮席位批判(cross/p2p)→ 主席综合 memo verdict。"""

    def __init__(self, seats: list[tuple[CommitteeSeat, LLMClient]], chair_client: LLMClient,
                 rounds: int = 1, mode: str = "cross", skill_desc: dict[str, str] | None = None, logger=None) -> None:
        self.runners = [SeatRunner(seat, client, skill_desc or {}, logger) for seat, client in seats]
        self.chair = ChairSynthesizer(chair_client, logger)
        self.rounds = max(1, min(int(rounds), 3))
        self.mode = mode if mode in ("cross", "p2p") else "cross"

    def convene(self, pending: PendingConvocation, context: str) -> CommitteeSession:
        remarks: list[SeatRemark] = []
        prev_round_texts: list[str] = []
        for round_no in range(1, self.rounds + 1):
            peers = prev_round_texts if (self.mode == "cross" and round_no > 1) else None
            this_round: list[str] = []
            for runner in self.runners:
                r = runner.critique(context, peers, round_no)
                if r is not None:
                    remarks.append(r)
                    this_round.append(f"{r.seat_name}({r.persona}): {r.critique}")
            prev_round_texts = this_round
        remarks_text = "\n".join(f"[第{r.round}轮] {r.seat_name}({r.persona}): {r.critique}" for r in remarks)
        verdict = self.chair.synthesize(context, remarks_text)
        return CommitteeSession(
            id=f"{pending.asset_id}_{now_iso()}", asset_id=pending.asset_id, asset_name=pending.asset_name,
            level=pending.level, seats=[r.seat for r in self.runners], rounds=self.rounds, mode=self.mode,
            remarks=remarks, verdict=verdict, created_at=now_iso())
