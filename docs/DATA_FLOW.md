# Data Flow & Storage Contract

This is the authoritative description of **who writes what, where, and who reads it**.
It exists because the UI pulls from three different backends; getting this wrong is
why pages can look inconsistent or "empty".

## The one rule

**`run_harness.py` is the single production path that writes narrative state.**
It accumulates and never wipes. Everything the UI shows about narratives comes from
what `run_harness` has written. `demo_runner.py` is an offline sandbox and must not
touch production data.

## Backends

| Store | Path | Holds | Written by | Read by |
|-------|------|-------|-----------|---------|
| **News DB** | `storage/macro_agents.sqlite3` | `news_items`, `analysis_cards`, `evidence_records`, `harness_sessions`, `harness_events`, `harness_compactions`, `harness_eval_runs` | `run_live_ingest` (news), `run_harness` (analysis/evidence/status + sessions/events) | Streamlit (Data, Operations), `eval_cli` |
| **Narrative state** | `storage/{main_narrative_state,branch_narrative_state,narrative_commits,alerts,scenarios}/` | the living narrative + its change history (commits) | `run_harness` → `UpdateNarrativeTool` (accumulates, **never clears**) | Streamlit (Research, Operations) |
| **Demo sandbox** | `storage/demo/...` | one-shot offline demo output | `demo_runner.py` (**clears its own dir each run**) | nobody (offline experiment only) |
| **QA report** | `storage/qa/ingestion_report.json` | fixture self-test of the ingest pipeline | `run_ingestion_qa.py` (fixtures, not real news) | Streamlit (Ingestion QA) |

## Production loop (the path that feeds the UI)

```
run_live_ingest.py   →  news_items (pending) in macro_agents.sqlite3
run_harness.py       →  reads pending news
                        → sort + analyze (LLM, rule fallback)  → analysis_cards/evidence_records in DB, status marked
                        → narrative update (LLM challenge judgment, rule fallback)
                          → ACCUMULATES into storage/{main_narrative_state,...}
                        → session + events in DB
Streamlit            →  reads DB (news/analysis/evidence/status) + storage/ (narrative)
eval_cli             →  reads harness_sessions/events from the SAME DB
```

## Why the timeline works

The narrative **evolution timeline** (strength/confidence over time) is reconstructable
from `storage/narrative_commits/` — each `NarrativeCommit` records `field_changes`
(`strength`/`confidence` `from`→`to`) plus `created_at`. Because `run_harness` accumulates
commits and never clears, the series grows continuously. This only holds as long as
**nothing wipes `storage/`** — which is exactly why `demo_runner` was moved to its own
sandbox (`storage/demo/`).

## Gotchas (do not reintroduce)

- ❌ Do not point `demo_runner` at the production `storage/` — it clears its output dir.
- ❌ Do not treat the **Ingestion QA** page as live data — it is a fixture self-test.
- ❌ Do not run two `HarnessCoordinator` tasks concurrently against one coordinator — the
  shared token meter is reset per task and is only safe sequentially.
- ✅ Keep `eval_cli --db` pointed at the same DB `run_harness` writes
  (`storage/macro_agents.sqlite3`, now the default).
