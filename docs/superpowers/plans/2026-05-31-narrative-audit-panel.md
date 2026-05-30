# Narrative Audit Panel Implementation Plan (v1.5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add an optional 0–3 seat auditor panel that critiques the Narrative Manager's challenge judgment over R rounds (seats see each other's prior-round critiques); the Narrative Manager then draws the final conclusion. Off by default; each seat independently keyed.

**Architecture:** `AuditPanel` runs the round-protocol debate and returns final-round critiques (pure debate, no decision). `NarrativeManagerAgent` gains an optional `audit_panel`; after its initial challenge judgment it asks the panel to critique, then re-judges via its narrative client. `build_run_loop` builds the panel from env (`NARRATIVE_AUDIT_SEATS/ROUNDS` + `LLM_AUDITOR_{1,2,3}_*`).

**Tech Stack:** existing `llm/`, `agents/`, `run_loop.py`. Stdlib only.

**Spec:** `docs/superpowers/specs/2026-05-31-narrative-audit-panel-design.md`

---

## Verified anchors

- `agents/narrative_manager.py` `__init__(self, knowledge_context=None, llm_client=None)`. In `update()` (lines ~63-72):
  ```python
  challenge_probability = relation_summary["challenge_probability"]
  branch_mode = relation_summary["branch_mode"]
  if self._llm_client is not None:
      try:
          challenge_probability, branch_mode = self._judge_challenge_with_llm(evidence_list, main_narrative)
      except (LLMError, ValueError, KeyError, TypeError):
          pass
  ```
  `main_narrative` (a `MainNarrative` with `core_claims`) and `evidence_list` (list of `Evidence` with `.relation_type`, `.claim`, `.strength`) are in scope. `clamp_score`, `LLMMessage`, `LLMError`, `json` already imported.
- `llm/base.py`: `LLMClient`, `LLMError`, `LLMMessage`, `LLMResponse`. `llm/fake.py`: `FakeLLMClient(responses=None, error=None)` with `.calls` recording each call's messages.
- `llm/config.load_llm_config(env=None, tier=None)` (reads `LLM_<TIER>_*` → bare `LLM_*`). `llm/factory.build_llm_client(config, transport=None) -> LLMClient | None`.
- `run_loop.build_run_loop(db_path, storage_root, config_path, run_now=False)`; `_interval(env_key, default)`; it builds `narrative_client` and `NarrativeManagerAgent(llm_client=narrative_client)`.
- `utils/logger.get_logger(name)`.

---

## File map

| File | Action |
|------|--------|
| `agents/audit.py` | Create `AuditPanel` (round protocol, peer-visible critiques, warn-on-fail) |
| `agents/narrative_manager.py` | Optional `audit_panel`; `_rejudge_with_critiques`; `_audit_context`; wrap challenge judgment |
| `run_loop.py` | `build_run_loop` builds panel from env + injects into NM |
| `.env.example` | Document audit seats/rounds + `LLM_AUDITOR_{1,2,3}_*` |
| `tests/test_audit_panel.py` | Create |
| `tests/test_narrative_manager_llm.py` | Append audit-integration tests |
| `tests/test_run_loop.py` | Append audit-wiring test |

---

### Task 1: AuditPanel

**Files:** Create `agents/audit.py`, `tests/test_audit_panel.py`.

- [ ] **Step 1: Write failing tests in `tests/test_audit_panel.py`**

```python
import json
import logging
import pytest
from agents.audit import AuditPanel
from llm.base import LLMError
from llm.fake import FakeLLMClient

_J = {"challenge_probability": 0.7, "open_branch": True}


def _critique(text):
    return json.dumps({"critique": text, "suggested_probability": None, "suggested_open_branch": None})


def test_no_seats_returns_empty():
    assert AuditPanel(seat_clients=[], rounds=1).deliberate(_J, "ctx") == []
    assert AuditPanel(seat_clients=[], rounds=1).seat_count == 0


def test_one_seat_one_round_returns_one_critique():
    seat = FakeLLMClient(responses=[_critique("overconfident")])
    out = AuditPanel(seat_clients=[seat], rounds=1).deliberate(_J, "ctx")
    assert out == ["overconfident"]


def test_two_rounds_second_sees_first_round_peer_critiques():
    # 2 seats x 2 rounds = 4 calls. Round-2 prompts must contain round-1 critiques.
    s1 = FakeLLMClient(responses=[_critique("c1r1"), _critique("c1r2")])
    s2 = FakeLLMClient(responses=[_critique("c2r1"), _critique("c2r2")])
    out = AuditPanel(seat_clients=[s1, s2], rounds=2).deliberate(_J, "ctx")
    assert out == ["c1r2", "c2r2"]  # final round
    # s1's 2nd call (round 2) should have seen peers' round-1 critiques (c1r1 / c2r1)
    round2_user = s1.calls[1][-1].content
    assert "c2r1" in round2_user or "c1r1" in round2_user


def test_failing_seat_is_skipped_with_warning(caplog):
    good = FakeLLMClient(responses=[_critique("ok")])
    bad = FakeLLMClient(error=LLMError("down"))
    with caplog.at_level(logging.WARNING):
        out = AuditPanel(seat_clients=[good, bad], rounds=1).deliberate(_J, "ctx")
    assert out == ["ok"]
    assert any("audit" in r.message.lower() for r in caplog.records)


def test_all_seats_fail_returns_empty():
    out = AuditPanel(seat_clients=[FakeLLMClient(error=LLMError("x"))], rounds=1).deliberate(_J, "ctx")
    assert out == []
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_audit_panel.py -v` → FAIL (`No module named 'agents.audit'`)

- [ ] **Step 3: Create `agents/audit.py`**

```python
from __future__ import annotations

import json

from llm.base import LLMClient, LLMError, LLMMessage
from utils.logger import get_logger


class AuditPanel:
    """0–3 auditor seats critique a judgment over R rounds. Round 1 is independent;
    each later round shows every seat the previous round's critiques. Returns the
    final round's critiques (pure debate — makes no decision). Failing seats are
    skipped with a warning; if no critiques survive, returns []."""

    def __init__(self, seat_clients: list[LLMClient], rounds: int = 1, logger=None) -> None:
        self._seats = list(seat_clients)
        self._rounds = max(1, min(int(rounds), 3))
        self._logger = logger or get_logger("macro_agents.audit")

    @property
    def seat_count(self) -> int:
        return len(self._seats)

    def deliberate(self, judgment: dict, context: str) -> list[str]:
        if not self._seats:
            return []
        prev: list[str] = []
        for round_no in range(1, self._rounds + 1):
            current: list[str] = []
            for index, client in enumerate(self._seats):
                try:
                    current.append(self._critique(client, judgment, context, prev if round_no > 1 else None))
                except (LLMError, ValueError, KeyError, TypeError) as exc:
                    self._logger.warning("audit seat %d failed in round %d: %s", index + 1, round_no, exc)
            prev = current
        return prev

    def _critique(self, client: LLMClient, judgment: dict, context: str, peers: list[str] | None) -> str:
        system = (
            "You are an auditor reviewing a macro narrative manager's judgment about whether "
            "incoming evidence challenges the mainline narrative. Critique it: is the challenge "
            "probability over/under-stated, is opening (or not) a branch justified? Respond with "
            "STRICT JSON only, no prose."
        )
        peer_block = ""
        if peers:
            peer_block = "\nOther auditors said:\n" + "\n".join(f"- {c}" for c in peers) + "\n"
        user = (
            f"Judgment: challenge_probability={judgment['challenge_probability']}, "
            f"open_branch={judgment['open_branch']}\n"
            f"Context:\n{context}\n{peer_block}\n"
            'Return JSON: {"critique": short string, "suggested_probability": 0..1 or null, '
            '"suggested_open_branch": true/false or null}.'
        )
        response = client.complete(
            [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
            temperature=0.0,
            max_tokens=4096,
        )
        data = json.loads(response.text)
        critique = data["critique"]
        if not isinstance(critique, str) or not critique.strip():
            raise ValueError("empty critique")
        return critique.strip()
```

- [ ] **Step 4: Run** → `pytest tests/test_audit_panel.py -v` → 5 pass.

- [ ] **Step 5: Commit**

```bash
git add agents/audit.py tests/test_audit_panel.py
git commit -m "feat(agents): AuditPanel — 0-3 seat R-round cross-critique debate"
```

---

### Task 2: NarrativeManager audit integration

**Files:** Modify `agents/narrative_manager.py`, append to `tests/test_narrative_manager_llm.py`.

- [ ] **Step 1: Append failing tests to `tests/test_narrative_manager_llm.py`**

```python
def test_audit_panel_rejudge_changes_outcome():
    # initial judge says no branch (supports); audit panel + rejudge flips to open_branch.
    import json as _j
    from agents.audit import AuditPanel
    initial = _j.dumps({"challenge_probability": 0.2, "open_branch": False})
    seat_resp = _j.dumps({"critique": "you understate the conflict", "suggested_probability": 0.8, "suggested_open_branch": True})
    rejudge = _j.dumps({"challenge_probability": 0.8, "open_branch": True})
    # NM narrative client: seed(identity) consumed first? Use a conflict evidence so no identity seed needed if core_claims preset.
    nm_client = FakeLLMClient(responses=[initial, rejudge])  # judge → rejudge
    panel = AuditPanel(seat_clients=[FakeLLMClient(responses=[seat_resp])], rounds=1)
    agent = NarrativeManagerAgent(llm_client=nm_client, audit_panel=panel)
    # preset state so identity-seeding doesn't consume a response
    from schemas.main_narrative import MainNarrative
    main = MainNarrative(id="main_default", title="美主线", region="US", theme="t", status="active",
        version=1, core_claims=["已立论"], supporting_evidence=[], counter_evidence=[], strength=0.6,
        confidence=0.6, market_consensus=0.5, market_priced=0.5, fragility=[], watch_items=[],
        replaced_by=None, effective_from="2026-05-31T00:00:00Z", updated_at="2026-05-31T00:00:00Z")
    state = {"main_narrative": main, "branches": [], "commits": [], "alerts": [], "scenarios": []}
    out = agent.update([_supports_evidence()], None, state)
    # rejudge forced open_branch True → a branch is created despite 'supports'
    assert len(out["branches"]) == 1


def test_no_audit_panel_keeps_initial_judgment():
    agent = NarrativeManagerAgent(llm_client=FakeLLMClient(responses=['{"challenge_probability":0.1,"open_branch":false}']))
    state = agent.update([_supports_evidence()], None, {})
    assert len(state["branches"]) == 0  # no panel, supports → no branch
```

- [ ] **Step 2: Run** → FAIL (`audit_panel` kwarg unknown).

- [ ] **Step 3: Edit `agents/narrative_manager.py`**

Change `__init__` to accept the panel:

```python
    def __init__(
        self,
        knowledge_context: dict | None = None,
        llm_client: LLMClient | None = None,
        audit_panel=None,
    ) -> None:
        self.knowledge_context = knowledge_context or {}
        self.last_knowledge_docs: dict[str, list[dict]] = {}
        self._llm_client = llm_client
        self.audit_panel = audit_panel
```

After the existing challenge-override block (the `if self._llm_client is not None: try: ... _judge_challenge_with_llm ...` ending at `pass  # fall back to rule-derived values`), add the audit step:

```python
        if (
            self._llm_client is not None
            and self.audit_panel is not None
            and self.audit_panel.seat_count > 0
        ):
            try:
                judgment = {"challenge_probability": challenge_probability, "open_branch": branch_mode}
                ctx = self._audit_context(main_narrative, evidence_list)
                critiques = self.audit_panel.deliberate(judgment, ctx)
                if critiques:
                    challenge_probability, branch_mode = self._rejudge_with_critiques(judgment, critiques, ctx)
            except (LLMError, ValueError, KeyError, TypeError):
                pass  # audit failure must never block the narrative update
```

Add the two helper methods (place near `_judge_challenge_with_llm`):

```python
    def _audit_context(self, main_narrative: MainNarrative, evidence_list: list[Evidence]) -> str:
        thesis = main_narrative.core_claims[0] if main_narrative.core_claims else main_narrative.title
        ev = "\n".join(f"- [{e.relation_type}] {e.claim} (strength={e.strength:.2f})" for e in evidence_list[:8])
        return f"Mainline thesis: {thesis}\nNew evidence:\n{ev or '(none)'}"

    def _rejudge_with_critiques(self, judgment: dict, critiques: list[str], context: str) -> tuple[float, bool]:
        system = (
            "You are a macro narrative manager. Auditors critiqued your judgment about whether "
            "incoming evidence challenges the mainline. Reconsider and give your FINAL judgment. "
            "Respond with STRICT JSON only, no prose."
        )
        crit_block = "\n".join(f"- {c}" for c in critiques)
        user = (
            f"Your initial judgment: challenge_probability={judgment['challenge_probability']}, "
            f"open_branch={judgment['open_branch']}\n"
            f"Context:\n{context}\n"
            f"Auditor critiques:\n{crit_block}\n\n"
            'Return JSON: {"challenge_probability": 0..1 float, "open_branch": boolean}.'
        )
        response = self._llm_client.complete(
            [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
            temperature=0.0,
            max_tokens=4096,
        )
        data = json.loads(response.text)
        open_branch = data["open_branch"]
        if not isinstance(open_branch, bool):
            raise ValueError("open_branch must be a boolean")
        return clamp_score(float(data["challenge_probability"])), open_branch
```

- [ ] **Step 4: Run** → `pytest tests/test_narrative_manager_llm.py tests/test_narrative_manager.py -v` → all pass.

- [ ] **Step 5: Commit**

```bash
git add agents/narrative_manager.py tests/test_narrative_manager_llm.py
git commit -m "feat(narrative): optional audit panel re-judges challenge call before concluding"
```

---

### Task 3: Wire panel into build_run_loop + .env.example

**Files:** Modify `run_loop.py`, `.env.example`, append to `tests/test_run_loop.py`.

- [ ] **Step 1: Append failing test to `tests/test_run_loop.py`**

```python
def test_build_run_loop_audit_seats(monkeypatch):
    import run_loop
    monkeypatch.setenv("OPENAI_API_KEY", "k")  # so clients build
    monkeypatch.setenv("NARRATIVE_AUDIT_SEATS", "2")
    monkeypatch.setenv("NARRATIVE_AUDIT_ROUNDS", "2")
    rl = run_loop.build_run_loop()
    # find the narrative manager via the consolidation stage closure is hard; instead rebuild check:
    # build_run_loop must attach a 2-seat panel to the narrative manager it created.
    # Expose via a module helper for testability:
    nm = run_loop._last_narrative_manager
    assert nm.audit_panel is not None and nm.audit_panel.seat_count == 2


def test_build_run_loop_no_audit_by_default(monkeypatch):
    import run_loop
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("NARRATIVE_AUDIT_SEATS", raising=False)
    run_loop.build_run_loop()
    assert run_loop._last_narrative_manager.audit_panel is None
```

- [ ] **Step 2: Run** → FAIL (`_last_narrative_manager` / panel not wired).

- [ ] **Step 3: Edit `run_loop.py` `build_run_loop`**

After building `narrative_client`, build the panel and the NM with it (replace the existing
`narrative_manager = NarrativeManagerAgent(llm_client=narrative_client)` line):

```python
    seats = max(0, min(int(_interval("NARRATIVE_AUDIT_SEATS", 0)), 3))
    rounds = int(_interval("NARRATIVE_AUDIT_ROUNDS", 1))
    audit_panel = None
    if seats > 0:
        from agents.audit import AuditPanel
        seat_clients = []
        for i in range(1, seats + 1):
            client = build_llm_client(load_llm_config(tier=f"auditor_{i}"))
            if client is not None:
                seat_clients.append(client)
        if seat_clients:
            audit_panel = AuditPanel(seat_clients, rounds=rounds)

    narrative_manager = NarrativeManagerAgent(llm_client=narrative_client, audit_panel=audit_panel)
```

Add a module-level testability hook: at the end of `build_run_loop`, just before `return RunLoop(stages)`, add:

```python
    global _last_narrative_manager
    _last_narrative_manager = narrative_manager
```

and near the top of `run_loop.py` (module level, after imports) add:

```python
_last_narrative_manager = None  # set by build_run_loop; used by tests/introspection
```

- [ ] **Step 4: Append to `.env.example`**

```bash

# --- Narrative audit panel (v1.5; off by default) ---
# NARRATIVE_AUDIT_SEATS=0          # 0 关闭;1-3 个审计席位
# NARRATIVE_AUDIT_ROUNDS=1         # 1-3 轮(席位互看批判)
# 每席独立 key(默认推理模型;不填回退 LLM_*):
# LLM_AUDITOR_1_MODEL=deepseek-reasoner
# LLM_AUDITOR_1_API_KEY=
# LLM_AUDITOR_2_MODEL=deepseek-reasoner
# LLM_AUDITOR_2_API_KEY=
# LLM_AUDITOR_3_MODEL=deepseek-reasoner
# LLM_AUDITOR_3_API_KEY=
```

- [ ] **Step 5: Run** → `pytest tests/test_run_loop.py -v` → all pass.

- [ ] **Step 6: Full suite** → `pytest -q` → all pass.

- [ ] **Step 7: Commit**

```bash
git add run_loop.py .env.example tests/test_run_loop.py
git commit -m "feat(run-loop): wire NARRATIVE_AUDIT_SEATS/ROUNDS + LLM_AUDITOR_* into narrative manager"
```

---

## Self-review notes

- Spec coverage: AuditPanel round protocol (T1), audit only the challenge judgment + NM concludes (T2), seats 0-3 / rounds 1-3 / per-seat keys / default off (T3), fail→skip+warn / never block (T1+T2). ✓
- Type consistency: `AuditPanel(seat_clients, rounds).deliberate(judgment: dict, context: str) -> list[str]`, `.seat_count`; `_rejudge_with_critiques(judgment, critiques, context) -> (float, bool)` used consistently.
- No schema/storage changes.
