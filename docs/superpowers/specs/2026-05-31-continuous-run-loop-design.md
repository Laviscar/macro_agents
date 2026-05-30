# Continuous Run Loop — Design Spec

**Date:** 2026-05-31
**Status:** Design (awaiting review → writing-plans)

## Goal

Turn macro_agents from manual one-shot runs into a single continuously-running process
that keeps news fresh, screens importance with a cheap LLM, analyzes only high-signal
items with a reasoning LLM, and consolidates the narrative on a calm 60-minute cadence —
with bounded cost.

## Decisions locked (from brainstorming)

1. **Orchestration:** one resident process `run_loop.py` with internal tiered timers.
2. **Narrative consolidation cadence:** every 60 minutes.
3. **Breaking/urgency fast-path:** out of scope for now (designed to be addable later).
4. **Triage:** two layers — program does exact dedup (already at insert time via
   `dedupe_key`), a cheap LLM judges importance.

## Non-goals (this iteration)

- Breaking-news fast path (urgency override). Designed-around, not built.
- Near-duplicate clustering (only exact dedup, which already exists at insert).
- LLM-driven NewsSorter scoring beyond a keep/skip importance judgment.

---

## Architecture

A single long-running orchestrator (`run_loop.py`) owns a scheduler with five stages,
each with its own interval and `last_run` timestamp. On each tick (~30s) the loop runs
whichever stages are due, in pipeline order, then sleeps. This mirrors the existing
`PollingIngestService` next-due pattern, generalized to multiple stages.

```
run_loop.py (resident)
  every tick (~30s): for each stage, if due → run(); update last_run
  stages (pipeline order):
    1. ingest          interval 300s    program        (5 min)
    2. triage          interval 900s    cheap LLM       (15 min)
    3. analysis        interval 900s    reasoning LLM   (15 min)
    4. consolidation   interval 3600s   reasoning LLM   (60 min)
    5. daily           interval 86400s  program (+ existing eval)
```

All intervals are env-configurable (see Config). The loop is stateless across stages
except for DB/storage; restarting it resumes cleanly from persisted state.

### Relationship to the existing harness

Today `coordinator.run_pending` runs the whole loop (sort → analyze → narrative) in one
batch. The new design **decouples analysis (stage 3) from consolidation (stage 4)** onto
different cadences, so the loop invokes **stage-level operations** rather than one
all-in-one batch. Each LLM-using stage may still be wrapped as its own harness session
(reusing `HarnessSessionStore` events + `BudgetGuard`) so logging, replay, and token
budgeting are preserved per stage. The existing `NarrativeLoopEngine`/`SortAndAnalyzeTool`
are refactored into these reusable stage operations; nothing about the schemas, agents,
or storage layout changes.

### Two LLM tiers

`llm/config.py` gains tier-aware loading:

- `load_llm_config(tier="triage")` reads `LLM_TRIAGE_*`, falling back to bare `LLM_*`.
- `load_llm_config(tier="analysis")` reads `LLM_ANALYSIS_*`, falling back to bare `LLM_*`.
- `load_llm_config()` (no tier) keeps current behavior (back-compat).

`run_loop` builds two clients: a cheap **triage client** and a reasoning **analysis
client**. The analysis client is injected into `AnalystAgent` + `NarrativeManagerAgent`
(as today). The triage client is injected into the new `TriageAgent`.

---

## Stages

### 1. Ingest (program)
Reuse the existing fetch path (`fetch_and_store_source`). One poll cycle per ingest
interval over enabled sources. Exact dedup already happens at insert (`INSERT OR IGNORE`
on `dedupe_key`). New rows land as `pending_sort`. No LLM.

### 2. Triage (cheap LLM)
New `TriageAgent` (uses the triage client). For each `pending_sort` item (batched):
- Build a compact prompt from title + summary + theme.
- Cheap LLM returns JSON `{ "important": bool, "reason": str }` (optionally a coarse
  theme tag). Bias the prompt toward **recall** for macro-critical themes (don't drop
  borderline items).
- **Important → status `pending_analysis`**; **not important → status `skipped`**.
- **Fallback ladder on triage-client failure** (error / bad JSON):
  1. retry the importance judgment with the **analysis (reasoning) client**, and emit a
     **WARNING** (the cheap tier is degraded — surfaced in logs and counted for the 系统
     page) so the user knows they're temporarily paying reasoning-model rates for triage;
  2. if the reasoning client also fails (or no client at all): **fail open** → mark
     `pending_analysis` (never silently drop news).
- `TriageAgent` therefore holds a primary (cheap) client and a fallback (reasoning) client.
- Batched with a per-cycle cap; remaining items wait for the next triage tick.

This **replaces the broken rule-based routing** (which scored real news at 0.5 and
skipped everything). The existing `NewsSorterAgent` still produces the `ResourceCard`
(normalization), but routing is decided by triage.

### 3. Analysis (reasoning LLM)
For `pending_analysis` items (batched, capped): run `AnalystAgent.analyze` +
`extract_evidence` with the **analysis (reasoning) client**, persist `analysis_cards` +
`evidence_records`, mark `analyzed`. Per-item error isolation (`mark_error`). This is the
existing `SortAndAnalyzeTool` analysis half, minus the routing (now done in triage).

### 4. Consolidation (reasoning LLM, every 60 min)
The calm digestion step. Uses a **watermark**:
- Read `last_consolidation_at` from a small persisted run-state (`storage/run_state.json`).
- Gather `evidence_records` (and their `analysis_cards`) with `created_at > watermark`.
- If none: no-op (advance nothing).
- Else: feed the accumulated evidence to `NarrativeManagerAgent` via the existing
  `update_from_evidence` + read-line/identity generation, write narrative state to
  `storage/`, then set `last_consolidation_at = now`.

This makes the narrative reflect a **batch of digested evidence once per hour**, not a
knee-jerk reaction to each headline — satisfying narrative stability.

### 5. Daily (program + eval)
Once per day: run `EvalScheduler` over the last window (existing), optionally
`CompactionService` on long sessions. Persisted eval run for the UI/metrics.

---

## Data & status model

```
ingest:        (new)            → pending_sort
triage:        pending_sort     → pending_analysis | skipped
analysis:      pending_analysis → analyzed   (+ analysis_cards, evidence_records)
consolidation: evidence since watermark → narrative state updated; watermark advanced
```

New repository methods:
- `list_news_by_status(status, limit)` — pull a status batch (generalizes
  `list_pending_news`).
- `get_evidence_since(timestamp) -> list[Evidence]` and a way to load the matching
  `analysis_cards` (e.g., `get_analysis_cards_since(timestamp)`), for consolidation.

Run-state: `storage/run_state.json` holds `{ "last_consolidation_at": ISO }` (and is the
natural home for future watermarks). Read/write via `utils.io`.

---

## Config (env, all optional with sane defaults)

```
# cadences (seconds)
RUN_LOOP_TICK_SECONDS=30
RUN_LOOP_INGEST_SECONDS=300          # 5 min
RUN_LOOP_TRIAGE_SECONDS=900          # 15 min
RUN_LOOP_ANALYSIS_SECONDS=900        # 15 min
RUN_LOOP_CONSOLIDATION_SECONDS=3600  # 60 min
RUN_LOOP_DAILY_SECONDS=86400

# batch caps (cost/backpressure)
RUN_LOOP_TRIAGE_BATCH=20
RUN_LOOP_ANALYSIS_BATCH=10

# two LLM tiers (fall back to bare LLM_* when unset)
LLM_TRIAGE_PROVIDER / LLM_TRIAGE_MODEL / LLM_TRIAGE_BASE_URL / LLM_TRIAGE_API_KEY(_ENV)
LLM_ANALYSIS_PROVIDER / LLM_ANALYSIS_MODEL / LLM_ANALYSIS_BASE_URL / LLM_ANALYSIS_API_KEY(_ENV)
```

`.env.example` documents these.

---

## Cost control

- Cheap-model triage filters noise so the reasoning model only sees high-signal items.
- Exact dedup at insert (existing) prevents reprocessing identical stories.
- Per-cycle batch caps (`*_BATCH`) bound spend and provide backpressure: if a backlog
  builds, it drains over multiple ticks (oldest-first), never a single spike.
- `BudgetGuard` token accounting already meters LLM usage per harness task; consolidation
  respects `LLM_TOKEN_BUDGET`.

## Error handling

- Each stage runs inside try/except; a failing stage logs and does not crash the loop or
  other stages.
- Per-item isolation in triage/analysis (`mark_error`), as today.
- LLM failures fall back: triage degrades to the reasoning client (with a WARNING),
  then fails open (→ pending_analysis) only if that also fails; analysis/narrative fall
  back to rule logic (existing behavior).
- SIGINT/SIGTERM → graceful stop (reuse the existing signal-handling pattern).

## Testing

- `TriageAgent`: FakeLLMClient → important/skip routing; on cheap-client failure, falls
  back to the reasoning client (asserts the warning is emitted); fails open
  (→ pending_analysis) only when both clients fail; no-client path.
- Tiered config: `load_llm_config("triage"/"analysis")` reads tier vars, falls back to
  `LLM_*`.
- Consolidation watermark: seed evidence with timestamps, assert only post-watermark
  evidence is consolidated and the watermark advances.
- Scheduler: a stage with a fake clock runs only when due; due stages run in pipeline
  order; one stage raising doesn't stop others.
- `run_loop` `drain_once()`/single-tick entrypoint is unit-testable without sleeping
  (inject clock + a max-ticks/once mode), mirroring `PollingIngestService.run_once`.

## Out of scope / future hooks

- **Breaking fast-path:** triage can later emit `urgency`; an urgent item would bypass
  cadence and trigger immediate analysis + a mini-consolidation. The stage structure
  leaves room (an extra status / priority queue) without redesign.
- **Near-duplicate clustering:** a future triage sub-step before importance.

---

## Implementation shape (files)

| File | Action |
|------|--------|
| `agents/triage.py` | Create `TriageAgent` (cheap primary + reasoning fallback client; importance judgment; warn-on-degrade; fail-open last resort) |
| `llm/config.py` | Add tier-aware `load_llm_config(tier=None)` |
| `repositories/news_repository.py` | Add `list_news_by_status`, `get_evidence_since`, `get_analysis_cards_since` |
| `harness/coordinator.py` | Split routing→triage; analysis uses analysis client |
| `pipelines/consolidation.py` (or harness) | Watermark-based consolidation over accumulated evidence |
| `run_loop.py` | Create the resident scheduler (stages, intervals, clock, once/tick mode) |
| `utils/io.py` | run_state.json read/write (reuse read_json/write_json) |
| `.env.example` | Document cadences + two LLM tiers |
| `tests/...` | Triage, tiered config, watermark consolidation, scheduler |
