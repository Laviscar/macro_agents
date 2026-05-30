# Continuous Run Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single resident `run_loop.py` that continuously ingests news, triages importance with a cheap LLM, analyzes high-signal items with a reasoning LLM, and consolidates the narrative every 60 minutes — bounded cost, no schema changes.

**Architecture:** Stage operations (ingest/triage/analyze/consolidate/daily) are plain functions; a small clock-injectable scheduler runs each when due. Two LLM tiers (cheap triage / reasoning analysis) are built from tier-aware config. Consolidation uses a persisted timestamp watermark so the narrative digests accumulated evidence once per hour.

**Tech Stack:** Python 3.11+, existing `llm/`, `agents/`, `harness/`, `repositories/`, `sources/`, `utils/` modules. Stdlib only. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-31-continuous-run-loop-design.md`

---

## Verified anchors

- `llm/config.py`: `load_llm_config(env=None) -> LLMConfig` reads `LLM_PROVIDER/MODEL/BASE_URL/API_KEY_ENV/API_KEY/TIMEOUT_SECONDS`. `LLMConfig(provider, model, api_key, base_url, timeout_seconds)` + `.is_configured`.
- `llm/factory.py`: `build_llm_client(config, transport=None) -> LLMClient | None`. `llm/fake.py`: `FakeLLMClient(responses=None, error=None)`.
- `llm/base.py`: `LLMMessage(role, content)`, `LLMResponse(text, input_tokens, output_tokens, raw)`, `LLMError`.
- `repositories/news_repository.py`: `list_pending_news(limit)` (status IN pending_sort/pending_analysis), `get_news_item(id)`, `save_resource_card(news_item_id, resource_card, status)`, `save_analysis_bundle(news_item_id, analysis_card, evidence_list)` (marks `analyzed`), `mark_error(news_item_id, msg)`, `get_status_counts()`. Connection at `self.connection` with `row_factory = sqlite3.Row`. `evidence_records(id, news_item_id, analysis_card_id, evidence_json, ..., created_at)`, `analysis_cards(id, news_item_id, analysis_card_json, ..., created_at)`.
- `harness/coordinator.py`: module-level `_load_or_build_resource_card(row, sorter) -> ResourceCard` and `load_narrative_state(storage_root) -> dict | None`. `SortAndAnalyzeTool`/`UpdateNarrativeTool` exist.
- `pipelines/narrative_update.py`: `update_from_evidence(evidence_list, analysis_cards, agent, state=None) -> dict` (pairs evidence to cards by `source_analysis_id == card.id`).
- `pipelines/live_ingest.py`: `build_polling_service(config, repository, logger=None) -> PollingIngestService` with `.run_once() -> list[SourcePollResult]`; `load_news_service_config(path)`, `resolve_news_service_config_path(path)`, `resolve_db_path(config_path, db_path_value)`, `APP_ROOT`.
- `agents/news_sorter.py`: `NewsSorterAgent().process(payload) -> ResourceCard` (ResourceCard has `id, title, one_liner, theme, ...`).
- `agents/analyst.py`: `AnalystAgent(knowledge_context=None, llm_client=None)`; `.analyze(rc, context) -> AnalysisCard`; `.extract_evidence(card, context) -> list[Evidence]`.
- `agents/narrative_manager.py`: `NarrativeManagerAgent(knowledge_context=None, llm_client=None)`; `.generate_read_line(main, evidence_list) -> str`.
- `utils/logger.py`: `get_logger(name) -> logging.Logger`, `log_event(logger, event, **fields)`.
- `utils/io.py`: `read_json(path, default=None)`, `write_json(path, data)`, `write_model(path, model)`, `write_models(dir, models)`, `read_models(dir, model_cls)`.
- `utils/clock.py`: `now_iso() -> str` (UTC ISO).
- `utils/dotenv.py`: `load_dotenv(path=".env")`.

---

## File map

| File | Action | Responsibility |
|------|--------|---------------|
| `llm/config.py` | Modify | tier-aware `load_llm_config(env=None, tier=None)` |
| `agents/triage.py` | Create | `TriageAgent` — cheap primary + reasoning fallback, warn-on-degrade, fail-open |
| `repositories/news_repository.py` | Modify | `list_news_by_status`, `get_evidence_since`, `get_analysis_cards_since` |
| `harness/coordinator.py` | Modify | extract `persist_narrative_state(state, storage_root)` (reused by stage + tool) |
| `pipelines/stages.py` | Create | `triage_pending`, `analyze_pending`, `consolidate` stage functions + run-state watermark |
| `run_loop.py` | Create | `Stage`, `RunLoop` scheduler (clock-injectable, tick/once + serve_forever), `build_run_loop` |
| `.env.example` | Modify | cadences + two LLM tiers |
| `tests/test_llm_config.py` | Modify | tier-aware reading + fallback |
| `tests/test_triage_agent.py` | Create | triage routing + degrade + fail-open |
| `tests/test_news_repository_queries.py` | Create | status + since-timestamp queries |
| `tests/test_pipeline_stages.py` | Create | triage/analyze/consolidate stage behavior + watermark |
| `tests/test_run_loop.py` | Create | scheduler due-logic, order, isolation, once mode |

---

### Task 1: Tier-aware LLM config

**Files:**
- Modify: `llm/config.py`
- Modify: `tests/test_llm_config.py`

- [ ] **Step 1: Append failing tests to `tests/test_llm_config.py`**

```python
def test_tier_reads_tier_specific_vars():
    cfg = load_llm_config(env={
        "LLM_PROVIDER": "openai", "LLM_MODEL": "base-model",
        "LLM_TRIAGE_MODEL": "cheap-model", "OPENAI_API_KEY": "k",
    }, tier="triage")
    assert cfg.model == "cheap-model"


def test_tier_falls_back_to_bare_llm_vars():
    cfg = load_llm_config(env={"LLM_MODEL": "base-model", "OPENAI_API_KEY": "k"}, tier="analysis")
    assert cfg.model == "base-model"  # no LLM_ANALYSIS_MODEL → falls back


def test_tier_specific_key_env():
    cfg = load_llm_config(env={
        "LLM_TRIAGE_API_KEY_ENV": "CHEAP_KEY", "CHEAP_KEY": "ck",
        "OPENAI_API_KEY": "base",
    }, tier="triage")
    assert cfg.api_key == "ck"


def test_no_tier_is_backwards_compatible():
    cfg = load_llm_config(env={"LLM_MODEL": "m", "OPENAI_API_KEY": "k"})
    assert cfg.model == "m" and cfg.api_key == "k"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_llm_config.py::test_tier_reads_tier_specific_vars -v`
Expected: FAIL (`load_llm_config() got an unexpected keyword argument 'tier'`)

- [ ] **Step 3: Replace `load_llm_config` body in `llm/config.py`**

```python
def load_llm_config(env: dict | None = None, tier: str | None = None) -> LLMConfig:
    """Build LLMConfig from environment. With `tier` (e.g. "triage"/"analysis"),
    `LLM_<TIER>_X` is read first, falling back to bare `LLM_X`. No secrets hard-coded.
    """
    env = env if env is not None else os.environ

    def g(key: str) -> str | None:
        if tier:
            v = env.get(f"LLM_{tier.upper()}_{key}")
            if v:
                return v
        return env.get(f"LLM_{key}")

    provider = (g("PROVIDER") or "openai").lower()
    model = g("MODEL") or _DEFAULT_MODEL.get(provider, "")
    base_url = g("BASE_URL") or _DEFAULT_BASE_URL.get(provider, "")
    key_env = g("API_KEY_ENV") or _DEFAULT_KEY_ENV.get(provider, "LLM_API_KEY")
    api_key = env.get(key_env) or g("API_KEY")
    try:
        timeout = float(g("TIMEOUT_SECONDS") or 30.0)
    except ValueError:
        timeout = 30.0
    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=timeout,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_llm_config.py -v`
Expected: all pass (existing 5 + 4 new). The existing no-tier tests still pass because `g(key)` with `tier=None` is exactly `env.get("LLM_" + key)`.

- [ ] **Step 5: Commit**

```bash
git add llm/config.py tests/test_llm_config.py
git commit -m "feat(llm): tier-aware load_llm_config (triage/analysis tiers, fallback to LLM_*)"
```

---

### Task 2: TriageAgent (cheap primary + reasoning fallback)

**Files:**
- Create: `agents/triage.py`
- Create: `tests/test_triage_agent.py`

`TriageAgent.is_important(resource_card) -> bool`. Tries the primary (cheap) client; on
`LLMError`/parse/validation failure it retries with the fallback (reasoning) client and
emits a WARNING + bumps `degraded_count`; if both fail (or no client), it **fails open**
(returns `True`, never silently drops news).

- [ ] **Step 1: Write failing tests in `tests/test_triage_agent.py`**

```python
import json
import logging
import pytest
from agents.triage import TriageAgent
from llm.base import LLMError
from llm.fake import FakeLLMClient
from schemas.resource_card import ResourceCard
from utils.clock import now_iso


def _card(title="US CPI cools more than expected") -> ResourceCard:
    return ResourceCard(
        id="rc_1", timestamp=now_iso(), source="test", url="https://x", title=title,
        one_liner="inflation slowed again", region=["Global"], theme=["inflation"],
        card_type="news", tags=[], importance_score=0.5, structural_score=0.5,
        timeliness_score=0.5, verifiability_score=0.5, analysis_readiness_score=0.5,
        route_to_analysis=False, route_decision="watchlist", archive_bucket="2026_05",
    )


def test_important_true_from_primary():
    primary = FakeLLMClient(responses=[json.dumps({"important": True, "reason": "macro"})])
    agent = TriageAgent(primary_client=primary)
    assert agent.is_important(_card()) is True


def test_unimportant_false_from_primary():
    primary = FakeLLMClient(responses=[json.dumps({"important": False, "reason": "noise"})])
    agent = TriageAgent(primary_client=primary)
    assert agent.is_important(_card()) is False


def test_degrades_to_fallback_and_warns(caplog):
    primary = FakeLLMClient(error=LLMError("cheap down"))
    fallback = FakeLLMClient(responses=[json.dumps({"important": True, "reason": "x"})])
    agent = TriageAgent(primary_client=primary, fallback_client=fallback)
    with caplog.at_level(logging.WARNING):
        result = agent.is_important(_card())
    assert result is True
    assert agent.degraded_count == 1
    assert any("triage" in r.message.lower() or "degrad" in r.message.lower() for r in caplog.records)


def test_fails_open_when_both_fail():
    primary = FakeLLMClient(error=LLMError("down"))
    fallback = FakeLLMClient(error=LLMError("also down"))
    agent = TriageAgent(primary_client=primary, fallback_client=fallback)
    assert agent.is_important(_card()) is True  # fail open


def test_fails_open_when_no_client():
    agent = TriageAgent(primary_client=None)
    assert agent.is_important(_card()) is True
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_triage_agent.py -v`
Expected: FAIL (`No module named 'agents.triage'`)

- [ ] **Step 3: Create `agents/triage.py`**

```python
from __future__ import annotations

import json

from llm.base import LLMClient, LLMError, LLMMessage
from schemas.resource_card import ResourceCard
from utils.logger import get_logger, log_event


class TriageAgent:
    """Cheap-LLM importance screen. Degrades to the reasoning client (with a warning)
    when the cheap client fails, and fails open (important=True) if both fail."""

    def __init__(
        self,
        primary_client: LLMClient | None = None,
        fallback_client: LLMClient | None = None,
        logger=None,
    ) -> None:
        self._primary = primary_client
        self._fallback = fallback_client
        self._logger = logger or get_logger("macro_agents.triage")
        self.degraded_count = 0

    def is_important(self, resource_card: ResourceCard) -> bool:
        messages = self._build_messages(resource_card)
        if self._primary is not None:
            try:
                return self._judge(self._primary, messages)
            except (LLMError, ValueError, KeyError, TypeError):
                pass
        if self._fallback is not None:
            try:
                result = self._judge(self._fallback, messages)
                self.degraded_count += 1
                log_event(
                    self._logger, "triage_degraded_to_fallback",
                    reason="primary triage client failed; used reasoning client",
                    title=resource_card.title[:80],
                )
                return result
            except (LLMError, ValueError, KeyError, TypeError):
                pass
        # fail open — never silently drop news
        return True

    def _judge(self, client: LLMClient, messages: list[LLMMessage]) -> bool:
        response = client.complete(messages, temperature=0.0, max_tokens=4096)
        data = json.loads(response.text)
        important = data["important"]
        if not isinstance(important, bool):
            raise ValueError("important must be a boolean")
        return important

    def _build_messages(self, resource_card: ResourceCard) -> list[LLMMessage]:
        system = (
            "You screen macro news for a research system. Decide if an item is important "
            "enough to deeply analyze. Bias toward keeping anything macro-relevant (policy, "
            "inflation, rates, growth, geopolitics, energy, FX, systemic risk). Respond with "
            "STRICT JSON only."
        )
        user = (
            f"Title: {resource_card.title}\n"
            f"Summary: {resource_card.one_liner}\n"
            f"Themes: {', '.join(resource_card.theme)}\n\n"
            'Return JSON: {"important": boolean, "reason": short string}.'
        )
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_triage_agent.py -v`
Expected: 5 pass

- [ ] **Step 5: Commit**

```bash
git add agents/triage.py tests/test_triage_agent.py
git commit -m "feat(agents): TriageAgent — cheap importance screen, reasoning fallback + warn, fail-open"
```

---

### Task 3: Repository query helpers

**Files:**
- Modify: `repositories/news_repository.py`
- Create: `tests/test_news_repository_queries.py`

- [ ] **Step 1: Write failing tests in `tests/test_news_repository_queries.py`**

```python
import pytest
from repositories.news_repository import SQLiteNewsRepository
from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence
from schemas.raw_news_item import RawNewsItem
from utils.clock import now_iso


def _repo(tmp_path):
    return SQLiteNewsRepository(tmp_path / "t.sqlite3")


def _item(title):
    return RawNewsItem(source_type="rss", source_name="s", external_id=title, url=f"https://x/{title}",
                       title=title, summary="s", published_at=now_iso(), fetched_at=now_iso(), raw_payload={})


def _card(cid, created_at):
    return AnalysisCard(id=cid, event_id="e", source_card_ids=["e"], reframed_question="q",
                        signal_level="structure", thesis="t", evidence_for=["x"], evidence_against=[],
                        macro_variables=["m"], asset_mapping=[], confidence=0.6, mainline_relation="supports",
                        candidate_branch_title=None, invalidation_conditions=[], created_at=created_at)


def _ev(eid, cid, created_at):
    return Evidence(id=eid, source_analysis_id=cid, source_card_ids=["e"], claim="c", relation_type="supports",
                    target_main_narrative_id="main_default", target_branch_id=None, strength=0.6, confidence=0.6,
                    why="w", counter_evidence=[], created_at=created_at)


def test_list_news_by_status(tmp_path):
    repo = _repo(tmp_path)
    repo.insert_news_item(_item("a"))
    rows = repo.list_news_by_status("pending_sort", limit=10)
    assert len(rows) == 1 and rows[0]["analysis_status"] == "pending_sort"
    assert repo.list_news_by_status("analyzed", limit=10) == []


def test_get_evidence_and_cards_since(tmp_path):
    repo = _repo(tmp_path)
    nid = repo.insert_news_item(_item("a"))
    repo.save_analysis_bundle(nid, _card("ac_old", "2026-05-30T10:00:00Z"), [_ev("ev_old", "ac_old", "2026-05-30T10:00:00Z")])
    repo.save_analysis_bundle(nid, _card("ac_new", "2026-05-31T10:00:00Z"), [_ev("ev_new", "ac_new", "2026-05-31T10:00:00Z")])
    ev = repo.get_evidence_since("2026-05-31T00:00:00Z")
    assert [e.id for e in ev] == ["ev_new"]
    cards = repo.get_analysis_cards_since("2026-05-31T00:00:00Z")
    assert [c.id for c in cards] == ["ac_new"]
    assert repo.get_evidence_since("2020-01-01T00:00:00Z")  # both
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_news_repository_queries.py -v`
Expected: FAIL (`'SQLiteNewsRepository' object has no attribute 'list_news_by_status'`)

- [ ] **Step 3: Add methods to `SQLiteNewsRepository` (after `list_pending_news`)**

```python
    def list_news_by_status(self, status: str, limit: int = 20) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM news_items
            WHERE analysis_status = ?
            ORDER BY COALESCE(published_at, fetched_at) ASC, id ASC
            LIMIT ?
            """,
            (status, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_evidence_since(self, created_after: str) -> list[Evidence]:
        rows = self.connection.execute(
            "SELECT evidence_json FROM evidence_records WHERE created_at > ? ORDER BY created_at ASC",
            (created_after,),
        ).fetchall()
        return [Evidence.model_validate_json(row["evidence_json"]) for row in rows]

    def get_analysis_cards_since(self, created_after: str) -> list[AnalysisCard]:
        rows = self.connection.execute(
            "SELECT analysis_card_json FROM analysis_cards WHERE created_at > ? ORDER BY created_at ASC",
            (created_after,),
        ).fetchall()
        return [AnalysisCard.model_validate_json(row["analysis_card_json"]) for row in rows]
```

(`AnalysisCard` and `Evidence` are already imported at the top of the file.)

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_news_repository_queries.py -v`
Expected: 2 pass

- [ ] **Step 5: Commit**

```bash
git add repositories/news_repository.py tests/test_news_repository_queries.py
git commit -m "feat(repo): list_news_by_status + get_evidence/analysis_cards_since"
```

---

### Task 4: Extract `persist_narrative_state`

**Files:**
- Modify: `harness/coordinator.py`
- Test: covered by existing `tests/test_harness_coordinator.py`

Extract the narrative write block so the consolidation stage (Task 5) reuses exactly what
`UpdateNarrativeTool` writes — no duplication.

- [ ] **Step 1: Add `persist_narrative_state` to `harness/coordinator.py` (after `load_narrative_state`)**

```python
def persist_narrative_state(state: dict, storage_root: str | Path) -> dict:
    """Write a narrative state dict to storage/ and return a small summary."""
    root = Path(storage_root)
    main_narrative = state["main_narrative"]
    ensure_dir(root / "main_narrative_state")
    write_model(root / "main_narrative_state" / f"{main_narrative.id}.json", main_narrative)
    write_models(root / "branch_narrative_state", state["branches"])
    write_models(root / "narrative_commits", state["commits"])
    write_models(root / "alerts", state["alerts"])
    write_models(root / "scenarios", state["scenarios"])
    return {
        "main_narrative_id": main_narrative.id,
        "branches_count": len(state["branches"]),
        "commits_count": len(state["commits"]),
    }
```

- [ ] **Step 2: Use it inside `UpdateNarrativeTool.execute`**

Replace the existing write block (the `ensure_dir(...)` + five `write_model`/`write_models`
lines and the `return ToolResult(... output={main_narrative_id, branches_count, commits_count})`
construction) with:

```python
        summary = persist_narrative_state(state, self.storage_root)
        return ToolResult(tool_name=self.name, success=True, output=summary)
```

(Keep everything above it — `load_narrative_state`, `update_from_evidence`, `generate_read_line`,
the core_claims bootstrap — unchanged. `main_narrative = state["main_narrative"]` may be removed if now unused.)

- [ ] **Step 3: Run the coordinator suite**

Run: `pytest tests/test_harness_coordinator.py -v`
Expected: all pass (behavior unchanged — same files written, same output keys).

- [ ] **Step 4: Commit**

```bash
git add harness/coordinator.py
git commit -m "refactor(harness): extract persist_narrative_state for reuse by consolidation stage"
```

---

### Task 5: Stage operations (triage / analyze / consolidate)

**Files:**
- Create: `pipelines/stages.py`
- Create: `tests/test_pipeline_stages.py`

Plain functions the loop calls. Reuse existing helpers; consolidation uses a timestamp
watermark persisted in `storage/run_state.json`.

- [ ] **Step 1: Write failing tests in `tests/test_pipeline_stages.py`**

```python
import json
import pytest
from agents.analyst import AnalystAgent
from agents.news_sorter import NewsSorterAgent
from agents.narrative_manager import NarrativeManagerAgent
from agents.triage import TriageAgent
from llm.fake import FakeLLMClient
from pipelines.stages import triage_pending, analyze_pending, consolidate
from repositories.news_repository import SQLiteNewsRepository
from schemas.raw_news_item import RawNewsItem
from utils.clock import now_iso


def _item(title):
    return RawNewsItem(source_type="rss", source_name="s", external_id=title, url=f"https://x/{title}",
                       title=title, summary="inflation cooled again", published_at=now_iso(),
                       fetched_at=now_iso(), raw_payload={})


def test_triage_routes_important_and_skips(tmp_path):
    repo = SQLiteNewsRepository(tmp_path / "t.sqlite3")
    repo.insert_news_item(_item("keep me"))
    repo.insert_news_item(_item("drop me"))
    primary = FakeLLMClient(responses=[
        json.dumps({"important": True, "reason": "x"}),
        json.dumps({"important": False, "reason": "y"}),
    ])
    triage = TriageAgent(primary_client=primary)
    result = triage_pending(repo, triage, NewsSorterAgent(), limit=10)
    assert result["important"] == 1 and result["skipped"] == 1
    assert len(repo.list_news_by_status("pending_analysis", 10)) == 1
    assert len(repo.list_news_by_status("skipped", 10)) == 1


def test_analyze_pending_produces_evidence(tmp_path):
    repo = SQLiteNewsRepository(tmp_path / "t.sqlite3")
    nid = repo.insert_news_item(_item("inflation cools"))
    # move it to pending_analysis via triage (fail-open, no client → important)
    triage_pending(repo, TriageAgent(primary_client=None), NewsSorterAgent(), limit=10)
    result = analyze_pending(repo, AnalystAgent(), limit=10)  # no llm → rule analysis
    assert result["analyzed"] >= 1
    assert len(repo.list_news_by_status("analyzed", 10)) >= 1
    assert repo.count_evidence_records() >= 1


def test_consolidate_uses_watermark(tmp_path):
    repo = SQLiteNewsRepository(tmp_path / "t.sqlite3")
    nid = repo.insert_news_item(_item("inflation cools lower than expected"))
    triage_pending(repo, TriageAgent(primary_client=None), NewsSorterAgent(), limit=10)
    analyze_pending(repo, AnalystAgent(), limit=10)
    storage = tmp_path / "storage"
    run_state = storage / "run_state.json"
    first = consolidate(repo, NarrativeManagerAgent(), storage, run_state)
    assert first["consolidated_evidence"] >= 1
    assert list((storage / "main_narrative_state").glob("*.json"))
    # second run: nothing new since watermark → no-op
    second = consolidate(repo, NarrativeManagerAgent(), storage, run_state)
    assert second["consolidated_evidence"] == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_pipeline_stages.py -v`
Expected: FAIL (`No module named 'pipelines.stages'`)

- [ ] **Step 3: Create `pipelines/stages.py`**

```python
from __future__ import annotations

from pathlib import Path

from agents.analyst import AnalystAgent
from agents.news_sorter import NewsSorterAgent
from agents.narrative_manager import NarrativeManagerAgent
from agents.triage import TriageAgent
from harness.coordinator import _load_or_build_resource_card, load_narrative_state, persist_narrative_state
from pipelines.narrative_update import update_from_evidence
from repositories.news_repository import SQLiteNewsRepository
from utils.clock import now_iso
from utils.io import read_json, write_json

_CONTEXT = {"target_main_narrative_id": "main_default"}


def triage_pending(
    repository: SQLiteNewsRepository,
    triage_agent: TriageAgent,
    sorter: NewsSorterAgent,
    limit: int = 20,
) -> dict:
    """pending_sort → pending_analysis (important) | skipped (not important)."""
    important = skipped = errors = 0
    for row in repository.list_news_by_status("pending_sort", limit=limit):
        nid = int(row["id"])
        try:
            card = _load_or_build_resource_card(row, sorter)
            keep = triage_agent.is_important(card)
            repository.save_resource_card(nid, card, status="pending_analysis" if keep else "skipped")
            important += int(keep)
            skipped += int(not keep)
        except Exception as exc:  # isolate one bad item
            repository.mark_error(nid, str(exc))
            errors += 1
    return {"important": important, "skipped": skipped, "errors": errors}


def analyze_pending(
    repository: SQLiteNewsRepository,
    analyst: AnalystAgent,
    limit: int = 10,
) -> dict:
    """pending_analysis → analyzed (+ analysis_cards / evidence_records)."""
    analyzed = errors = 0
    sorter = NewsSorterAgent()
    for row in repository.list_news_by_status("pending_analysis", limit=limit):
        nid = int(row["id"])
        try:
            card = _load_or_build_resource_card(row, sorter)
            analysis_card = analyst.analyze(card, context=_CONTEXT)
            evidence = analyst.extract_evidence(analysis_card, context=_CONTEXT)
            repository.save_analysis_bundle(nid, analysis_card, evidence)
            analyzed += 1
        except Exception as exc:
            repository.mark_error(nid, str(exc))
            errors += 1
    return {"analyzed": analyzed, "errors": errors}


def consolidate(
    repository: SQLiteNewsRepository,
    narrative_manager: NarrativeManagerAgent,
    storage_root: str | Path,
    run_state_path: str | Path,
) -> dict:
    """Digest evidence created since the last consolidation watermark into the narrative."""
    state_doc = read_json(run_state_path, default={}) or {}
    watermark = state_doc.get("last_consolidation_at", "")

    evidence_list = repository.get_evidence_since(watermark) if watermark else repository.get_evidence_since("")
    if not evidence_list:
        return {"consolidated_evidence": 0}

    analysis_cards = repository.get_analysis_cards_since(watermark) if watermark else repository.get_analysis_cards_since("")
    prior_state = load_narrative_state(storage_root)
    state = update_from_evidence(
        evidence_list=evidence_list,
        analysis_cards=analysis_cards,
        agent=narrative_manager,
        state=prior_state,
    )
    read_line = narrative_manager.generate_read_line(state["main_narrative"], evidence_list)
    updates = {"read_line": read_line}
    if not state["main_narrative"].core_claims or state["main_narrative"].core_claims == ["待定义"]:
        updates["core_claims"] = [read_line]
    state["main_narrative"] = state["main_narrative"].model_copy(update=updates)

    persist_narrative_state(state, storage_root)
    state_doc["last_consolidation_at"] = now_iso()
    write_json(run_state_path, state_doc)
    return {"consolidated_evidence": len(evidence_list)}
```

Note on `get_evidence_since("")`: an empty watermark string is less than any ISO timestamp,
so `created_at > ""` returns all evidence — correct for the first-ever consolidation.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_pipeline_stages.py -v`
Expected: 3 pass

- [ ] **Step 5: Commit**

```bash
git add pipelines/stages.py tests/test_pipeline_stages.py
git commit -m "feat(pipelines): triage/analyze/consolidate stage ops + watermark consolidation"
```

---

### Task 6: RunLoop scheduler

**Files:**
- Create: `run_loop.py`
- Create: `tests/test_run_loop.py`

A clock-injectable scheduler: each `Stage(name, interval, run_fn)` runs when due; `tick(now)`
runs all due stages in order, isolating exceptions; `serve_forever()` is the resident driver.

- [ ] **Step 1: Write failing tests in `tests/test_run_loop.py`**

```python
import pytest
from run_loop import Stage, RunLoop


def test_stage_runs_only_when_due():
    calls = []
    loop = RunLoop([Stage("a", interval_seconds=100, run_fn=lambda: calls.append("a"))])
    loop.tick(now=0.0)      # first tick always runs (never run before)
    loop.tick(now=50.0)     # not due yet
    loop.tick(now=100.0)    # due again
    assert calls == ["a", "a"]


def test_stages_run_in_order_when_due():
    order = []
    loop = RunLoop([
        Stage("first", interval_seconds=10, run_fn=lambda: order.append("first")),
        Stage("second", interval_seconds=10, run_fn=lambda: order.append("second")),
    ])
    loop.tick(now=0.0)
    assert order == ["first", "second"]


def test_one_stage_failure_does_not_stop_others():
    ran = []
    def boom():
        raise RuntimeError("stage failed")
    loop = RunLoop([
        Stage("bad", interval_seconds=10, run_fn=boom),
        Stage("good", interval_seconds=10, run_fn=lambda: ran.append("good")),
    ])
    loop.tick(now=0.0)  # must not raise
    assert ran == ["good"]


def test_run_once_runs_all_stages_regardless_of_interval():
    ran = []
    loop = RunLoop([Stage("a", interval_seconds=99999, run_fn=lambda: ran.append("a"))])
    loop.run_once()
    assert ran == ["a"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_run_loop.py -v`
Expected: FAIL (`No module named 'run_loop'`)

- [ ] **Step 3: Create `run_loop.py`**

```python
from __future__ import annotations

import argparse
import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Callable

from utils.logger import get_logger, log_event


@dataclass
class Stage:
    name: str
    interval_seconds: float
    run_fn: Callable[[], object]
    last_run: float | None = field(default=None)

    def is_due(self, now: float) -> bool:
        return self.last_run is None or (now - self.last_run) >= self.interval_seconds


class RunLoop:
    def __init__(self, stages: list[Stage], logger=None) -> None:
        self.stages = stages
        self._logger = logger or get_logger("macro_agents.run_loop")
        self._stop = Event()

    def tick(self, now: float) -> None:
        for stage in self.stages:
            if not stage.is_due(now):
                continue
            stage.last_run = now
            try:
                result = stage.run_fn()
                log_event(self._logger, "stage_ran", stage=stage.name, result=result)
            except Exception as exc:  # isolate; never crash the loop
                log_event(self._logger, "stage_failed", stage=stage.name, error=str(exc))

    def run_once(self) -> None:
        """Run every stage once, ignoring intervals (for manual/test runs)."""
        for stage in self.stages:
            try:
                stage.run_fn()
            except Exception as exc:
                log_event(self._logger, "stage_failed", stage=stage.name, error=str(exc))

    def stop(self) -> None:
        self._stop.set()

    def serve_forever(self, tick_seconds: float = 30.0) -> None:
        signal.signal(signal.SIGINT, lambda *_: self.stop())
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        log_event(self._logger, "run_loop_started", stages=[s.name for s in self.stages])
        while not self._stop.is_set():
            self.tick(now=time.monotonic())
            self._stop.wait(timeout=tick_seconds)
        log_event(self._logger, "run_loop_stopped")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_run_loop.py -v`
Expected: 4 pass

- [ ] **Step 5: Commit**

```bash
git add run_loop.py tests/test_run_loop.py
git commit -m "feat: RunLoop scheduler (due-based stages, ordered, isolated, once mode)"
```

---

### Task 7: Wire stages + two LLM tiers into `run_loop.py`

**Files:**
- Modify: `run_loop.py`
- Modify: `.env.example`

Add `build_run_loop()` that assembles the five stages from env config + the two LLM tiers,
plus a `main()` entry point.

- [ ] **Step 1: Append `build_run_loop` + `main` to `run_loop.py`**

```python
def _interval(env_key: str, default: float) -> float:
    try:
        return float(os.environ.get(env_key) or default)
    except ValueError:
        return default


def build_run_loop(
    db_path: str | Path = "storage/macro_agents.sqlite3",
    storage_root: str | Path = "storage",
    config_path: str | Path = "config/sources.yaml",
) -> "RunLoop":
    from agents.analyst import AnalystAgent
    from agents.narrative_manager import NarrativeManagerAgent
    from agents.news_sorter import NewsSorterAgent
    from agents.triage import TriageAgent
    from llm.config import load_llm_config
    from llm.factory import build_llm_client
    from pipelines.live_ingest import build_polling_service, load_news_service_config, resolve_news_service_config_path
    from pipelines.stages import analyze_pending, consolidate, triage_pending
    from repositories.news_repository import SQLiteNewsRepository

    repository = SQLiteNewsRepository(db_path)
    storage_root = Path(storage_root)
    run_state_path = storage_root / "run_state.json"

    triage_client = build_llm_client(load_llm_config(tier="triage"))
    analysis_client = build_llm_client(load_llm_config(tier="analysis"))

    sorter = NewsSorterAgent()
    triage_agent = TriageAgent(primary_client=triage_client, fallback_client=analysis_client)
    analyst = AnalystAgent(llm_client=analysis_client)
    narrative_manager = NarrativeManagerAgent(llm_client=analysis_client)

    cfg_path = resolve_news_service_config_path(Path(config_path)).resolve()
    ingest_service = build_polling_service(load_news_service_config(cfg_path), repository)

    triage_batch = int(_interval("RUN_LOOP_TRIAGE_BATCH", 20))
    analysis_batch = int(_interval("RUN_LOOP_ANALYSIS_BATCH", 10))

    stages = [
        Stage("ingest", _interval("RUN_LOOP_INGEST_SECONDS", 300), ingest_service.run_once),
        Stage("triage", _interval("RUN_LOOP_TRIAGE_SECONDS", 900),
              lambda: triage_pending(repository, triage_agent, sorter, limit=triage_batch)),
        Stage("analysis", _interval("RUN_LOOP_ANALYSIS_SECONDS", 900),
              lambda: analyze_pending(repository, analyst, limit=analysis_batch)),
        Stage("consolidation", _interval("RUN_LOOP_CONSOLIDATION_SECONDS", 3600),
              lambda: consolidate(repository, narrative_manager, storage_root, run_state_path)),
    ]
    return RunLoop(stages)


def main(argv: list[str] | None = None) -> None:
    from utils.dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the continuous macro_agents loop.")
    parser.add_argument("--db", default="storage/macro_agents.sqlite3")
    parser.add_argument("--storage-root", default="storage")
    parser.add_argument("--config", default="config/sources.yaml")
    parser.add_argument("--once", action="store_true", help="Run each stage once and exit.")
    args = parser.parse_args(argv)
    loop = build_run_loop(db_path=args.db, storage_root=args.storage_root, config_path=args.config)
    if args.once:
        loop.run_once()
    else:
        loop.serve_forever(tick_seconds=_interval("RUN_LOOP_TICK_SECONDS", 30))


if __name__ == "__main__":
    main()
```

(The daily eval stage is intentionally deferred to keep this plan focused; the existing
`eval_cli` covers evaluation and can be added as a 5th `Stage` later without redesign.)

- [ ] **Step 2: Append to `.env.example`**

```bash

# --- Continuous run loop (run_loop.py) ---
# RUN_LOOP_TICK_SECONDS=30
# RUN_LOOP_INGEST_SECONDS=300          # 5 min
# RUN_LOOP_TRIAGE_SECONDS=900          # 15 min
# RUN_LOOP_ANALYSIS_SECONDS=900        # 15 min
# RUN_LOOP_CONSOLIDATION_SECONDS=3600  # 60 min
# RUN_LOOP_TRIAGE_BATCH=20
# RUN_LOOP_ANALYSIS_BATCH=10

# --- Two LLM tiers (fall back to bare LLM_* when unset) ---
# LLM_TRIAGE_MODEL=deepseek-chat            # cheap importance screen
# LLM_TRIAGE_BASE_URL=https://api.deepseek.com
# LLM_ANALYSIS_MODEL=deepseek-reasoner      # reasoning analysis + narrative
# LLM_ANALYSIS_BASE_URL=https://api.deepseek.com
# (provider/key default to the bare LLM_* / OPENAI_API_KEY unless overridden per tier)
```

- [ ] **Step 3: Verify the loop assembles and runs one cycle (no LLM keys needed → rule fallback)**

Run:
```bash
python -c "import run_loop; rl = run_loop.build_run_loop(db_path='storage/macro_agents.sqlite3'); print('stages:', [s.name for s in rl.stages])"
```
Expected: prints `stages: ['ingest', 'triage', 'analysis', 'consolidation']` with no error.

- [ ] **Step 4: Run the full targeted suite**

Run: `pytest tests/test_run_loop.py tests/test_pipeline_stages.py tests/test_triage_agent.py tests/test_news_repository_queries.py tests/test_llm_config.py tests/test_harness_coordinator.py -v`
Expected: all pass.

- [ ] **Step 5: Run the whole suite to confirm no regressions**

Run: `pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add run_loop.py .env.example
git commit -m "feat: assemble run_loop stages + two LLM tiers; --once mode; .env.example"
```

---

## Self-review notes

- **Spec coverage:** tiered config (T1), TriageAgent degrade+warn+fail-open (T2), repo helpers (T3), watermark consolidation (T5), staged scheduler with 5/15/15/60 cadences (T6/T7), two LLM tiers + .env (T7), exact dedup reused at insert (no task needed — existing). Daily/eval stage explicitly deferred with a note.
- **No schema/storage changes:** confirmed — only new query methods + a `run_state.json` file.
- **Type consistency:** `is_important(resource_card) -> bool`, `triage_pending/analyze_pending/consolidate` signatures, `load_llm_config(env, tier)`, `Stage`/`RunLoop` are used identically across tasks.
- **Backpressure/cost:** batch caps (`RUN_LOOP_*_BATCH`) bound per-cycle LLM calls; triage filters before analysis.
