# Narrative Audit Panel — Design Spec

**Date:** 2026-05-31
**Status:** Design (awaiting confirm → writing-plans)

## Goal

Add an optional **audit/debate layer** to narrative management: before the Narrative
Manager finalizes a high-stakes judgment, 0–3 independently-keyed auditor LLMs critique it
over a configurable number of rounds; the Narrative Manager then draws the final
conclusion. This raises calibration on the judgments that move the narrative the most.

## Decisions locked (from discussion)

1. **What is audited:** only the high-risk judgment — `challenge_probability` + `open_branch`
   (whether to open a challenge branch). The current main thesis is given as context.
2. **Multi-round protocol:**
   - Round 1: each seat critiques the judgment independently.
   - Round r (2..R): each seat sees **all seats' round (r-1) critiques** (peers + its own)
     and produces a refined critique.
   - After R rounds: the Narrative Manager receives the **final-round critiques** from all
     seats and produces the final judgment.
3. **Seats:** `NARRATIVE_AUDIT_SEATS` ∈ {0,1,2,3}; default **0 (off)**.
   **Rounds:** `NARRATIVE_AUDIT_ROUNDS` ∈ {1,2,3}; default **1**.
4. **Auditor model:** reasoning model by default; **each seat independently keyed**
   (`LLM_AUDITOR_{1,2,3}_*`, falling back to bare `LLM_*`).

## Non-goals

- Auditing the thesis text or evidence extraction (only the challenge judgment).
- Auditors deciding the outcome — they only critique; the Narrative Manager concludes.

---

## Architecture

```
NarrativeManager initial judgment  J0 = {challenge_probability, open_branch}
  (existing _judge_challenge_with_llm; thesis + evidence summary kept as context)

if seats >= 1:
    critiques = AuditPanel(seat_clients, rounds).deliberate(J0, context)
        round 1: each seat → critique(J0, context)                 [independent]
        round r>1: each seat → critique(J0, context, peers_prev)   [sees peers]
        returns the final round's critiques (list[str], one per seat that responded)
    J_final = NarrativeManager._rejudge_with_critiques(J0, critiques, context)
else:
    J_final = J0

→ J_final feeds the existing branch/alert/commit construction unchanged.
```

### Components

- **`agents/audit.py` → `AuditPanel`**
  - `__init__(self, seat_clients: list[LLMClient], rounds: int = 1, logger=None)`
  - `.deliberate(judgment: dict, context: str) -> list[str]` — runs the round protocol,
    returns the final-round critiques. Pure debate; makes no decision.
  - Per-seat, per-round LLM failure → that seat contributes nothing that round + a WARNING
    (reuse logger). If no critiques are produced at all, returns `[]`.
  - With 1 seat and rounds>1, the single seat refines its own critique each round (it sees
    its own prior critique as the only "peer").

- **`agents/narrative_manager.py`** gains optional `audit_panel: AuditPanel | None`:
  - After `_judge_challenge_with_llm` yields `(challenge_probability, open_branch)`, if a
    panel with ≥1 seat is present: `critiques = audit_panel.deliberate(...)`; then
    `_rejudge_with_critiques(...)` (one call on the **narrative** client) returns the final
    `(challenge_probability, open_branch)`.
  - Failure / empty critiques / no panel → keep J0 (never block). Rule-only path (no
    narrative client) → no audit (J0 from rules stands).

### Config

```
NARRATIVE_AUDIT_SEATS=0          # 0 off; 1-3 seats
NARRATIVE_AUDIT_ROUNDS=1         # 1-3 rounds of cross-critique
LLM_AUDITOR_1_*                  # seat 1 (provider/model/base_url/api_key); reasoning default
LLM_AUDITOR_2_*                  # seat 2
LLM_AUDITOR_3_*                  # seat 3
```
Built via `load_llm_config(tier=f"auditor_{i}")` (already supports arbitrary tiers, falls
back to bare `LLM_*`). `build_run_loop` constructs the panel from the first `SEATS` configured
seats and injects it into the Narrative Manager.

### Prompts (shape)

- **Critique** (auditor): given J0 (`challenge_probability`, `open_branch`), the main thesis,
  and an evidence summary (+ peers' prior critiques in rounds>1), return STRICT JSON
  `{"critique": str, "suggested_probability": 0..1|null, "suggested_open_branch": bool|null}`.
  The `critique` text is what's passed forward; suggestions are advisory context for the NM.
- **Re-judge** (narrative manager): given J0 + the final critiques, return STRICT JSON
  `{"challenge_probability": 0..1, "open_branch": bool}`. Clamp probability; validate bool;
  on failure keep J0.

---

## Cost

Per consolidation with `S` seats × `R` rounds: `S×R` critique calls + (when S≥1) 1 re-judge
call. E.g. 1×1 → +2; 3×2 → +7. Consolidation runs ~hourly, so bounded. Default off = 0 extra.

## Error handling

- Any auditor/re-judge LLM failure degrades gracefully to J0 with a WARNING; the narrative
  update always proceeds.
- Seats are capped at 3 and rounds at 3 (clamp out-of-range env values).

## Testing

- `AuditPanel.deliberate`: 1 seat/1 round → one critique; 2 seats/2 rounds → second-round
  prompt includes peers' first-round critiques (assert via a recording FakeLLMClient);
  a failing seat is skipped with a warning; all-fail → `[]`.
- `NarrativeManager` with a panel: critiques change the final judgment vs J0 (re-judge
  applied); panel failure / no panel → J0 unchanged; rule-only path unaffected.
- `build_run_loop`: `NARRATIVE_AUDIT_SEATS=2` builds a 2-seat panel injected into the NM;
  `=0` → no panel; out-of-range values clamp to [0,3] / [1,3].

## Files

| File | Action |
|------|--------|
| `agents/audit.py` | Create `AuditPanel` (round protocol, peer-visible critiques, warn-on-fail) |
| `agents/narrative_manager.py` | Optional `audit_panel`; `_rejudge_with_critiques`; wrap challenge judgment |
| `run_loop.py` | `build_run_loop` builds panel from `NARRATIVE_AUDIT_SEATS/ROUNDS` + seat clients, injects into NM |
| `.env.example` | Document audit seats/rounds + `LLM_AUDITOR_{1,2,3}_*` |
| `tests/...` | AuditPanel protocol, NM re-judge, build_run_loop wiring |
