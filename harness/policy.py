from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from utils.clock import now_iso


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK_FOR_APPROVAL = "ask_for_approval"


@dataclass(frozen=True)
class PolicyRecord:
    tool_name: str
    risk_level: RiskLevel
    decision: PolicyDecision
    reason: str
    created_at: str


class PolicyEngine:
    """Stateless policy evaluator. One instance can be shared across sessions."""

    def evaluate(self, tool_name: str, risk_level: RiskLevel) -> tuple[PolicyDecision, str]:
        """Return (decision, reason) for a tool at the given risk level."""
        if risk_level == RiskLevel.LOW:
            return PolicyDecision.ALLOW, "low-risk reads are always allowed"
        if risk_level == RiskLevel.MEDIUM:
            return PolicyDecision.ALLOW, "local writes are allowed with audit"
        if risk_level == RiskLevel.HIGH:
            return PolicyDecision.ASK_FOR_APPROVAL, "external calls require approval"
        return PolicyDecision.DENY, "critical actions are denied by default"

    def record(self, tool_name: str, risk_level: RiskLevel) -> PolicyRecord:
        """Evaluate and return a frozen PolicyRecord for audit logging."""
        decision, reason = self.evaluate(tool_name, risk_level)
        return PolicyRecord(
            tool_name=tool_name,
            risk_level=risk_level,
            decision=decision,
            reason=reason,
            created_at=now_iso(),
        )
