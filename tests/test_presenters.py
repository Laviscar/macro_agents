from pathlib import Path

from pipelines.db_consumer import consume_pending_news
from presenters.data_presenter import build_news_detail_view, build_news_list_items
from presenters.operations_presenter import build_operations_overview
from presenters.research_presenter import build_research_overview
from agents.analyst import AnalystAgent
from agents.news_sorter import NewsSorterAgent
from repositories.news_repository import SQLiteNewsRepository
from schemas.raw_news_item import RawNewsItem


def _seed_repository(tmp_path: Path) -> SQLiteNewsRepository:
    repository = SQLiteNewsRepository(tmp_path / "macro.sqlite3")
    repository.insert_news_item(
        RawNewsItem(
            source_type="rss",
            source_name="example_rss",
            external_id="item-1",
            url="https://example.com/cpi-cools",
            title="US CPI cools in March",
            summary="Inflation data came in softer than expected.",
            published_at="2026-03-30T08:00:00+00:00",
            fetched_at="2026-03-30T08:05:00+00:00",
            raw_payload={
                "title": "US CPI cools in March",
                "summary": "Inflation data came in softer than expected.",
                "source": "example_rss",
                "url": "https://example.com/cpi-cools",
                "region": ["US"],
                "theme": ["inflation"],
                "importance_score": 0.9,
                "structural_score": 0.8,
                "verifiability_score": 0.9,
                "timestamp": "2026-03-30T08:00:00+00:00",
            },
        )
    )
    consume_pending_news(
        repository=repository,
        sorter=NewsSorterAgent(),
        analyst=AnalystAgent(),
    )
    return repository


def _seed_storage(tmp_path: Path) -> Path:
    storage_root = tmp_path / "storage"
    (storage_root / "main_narrative_state").mkdir(parents=True)
    (storage_root / "branch_narrative_state").mkdir(parents=True)
    (storage_root / "narrative_commits").mkdir(parents=True)
    (storage_root / "alerts").mkdir(parents=True)
    (storage_root / "scenarios").mkdir(parents=True)

    (storage_root / "main_narrative_state" / "main_default.json").write_text(
        """
{
  "id": "main_default",
  "title": "默认主线",
  "region": "Global",
  "theme": "macro_regime",
  "status": "active",
  "version": 1,
  "core_claims": ["通胀正在温和回落"],
  "supporting_evidence": ["ev_1"],
  "counter_evidence": [],
  "strength": 0.57,
  "confidence": 0.55,
  "market_consensus": 0.5,
  "market_priced": 0.5,
  "fragility": ["服务通胀仍需观察"],
  "watch_items": ["下次 CPI"],
  "replaced_by": null,
  "effective_from": "2026-03-30T08:00:00+00:00",
  "updated_at": "2026-03-30T08:07:00+00:00"
}
        """.strip(),
        encoding="utf-8",
    )
    (storage_root / "narrative_commits" / "commit_1.json").write_text(
        """
{
  "id": "commit_1",
  "narrative_type": "main",
  "narrative_id": "main_default",
  "source_evidence_ids": ["ev_1"],
  "action": "update",
  "summary": "默认主线 因 supports evidence 被强化",
  "field_changes": {"strength": {"from": 0.5, "to": 0.57}},
  "created_at": "2026-03-30T08:07:00+00:00"
}
        """.strip(),
        encoding="utf-8",
    )
    (storage_root / "alerts" / "_status.json").write_text(
        '{"status": "no_alert", "message": "No challenge alert generated for this demo run."}',
        encoding="utf-8",
    )
    return storage_root


def test_research_presenter_builds_research_overview(tmp_path: Path) -> None:
    storage_root = _seed_storage(tmp_path)

    overview = build_research_overview(storage_root)

    assert overview.global_headline != ""
    assert len(overview.main_cards) == 1
    assert overview.main_cards[0].narrative_id == "main_default"
    assert overview.main_cards[0].reinforcing_factors == ["ev_1"]
    assert overview.main_cards[0].watch_items == ["下次 CPI"]


def test_operations_presenter_builds_operations_overview(tmp_path: Path) -> None:
    repository = _seed_repository(tmp_path)
    storage_root = _seed_storage(tmp_path)

    overview = build_operations_overview(repository, storage_root)

    assert overview.analyst.analyzed_count == 1
    assert overview.analyst.evidence_generated_count == 1
    assert overview.narrative_manager.commit_count == 1
    assert overview.pipeline_health.analyzed_count == 1


def test_operations_presenter_does_not_require_raw_sqlite_connection_access(tmp_path: Path) -> None:
    repository = _seed_repository(tmp_path)
    storage_root = _seed_storage(tmp_path)

    class RepositoryProxy:
        def __init__(self, wrapped: SQLiteNewsRepository) -> None:
            self._wrapped = wrapped

        def get_status_counts(self):
            return self._wrapped.get_status_counts()

        def list_news_items(self, limit: int = 50):
            return self._wrapped.list_news_items(limit=limit)

        def count_evidence_records(self):
            return self._wrapped.count_evidence_records()

        def get_latest_analysis_created_at(self):
            return self._wrapped.get_latest_analysis_created_at()

    overview = build_operations_overview(RepositoryProxy(repository), storage_root)

    assert overview.analyst.analyzed_count == 1
    assert overview.pipeline_health.latest_analysis_at == repository.get_latest_analysis_created_at()


def test_data_presenter_builds_news_list_and_detail_views(tmp_path: Path) -> None:
    repository = _seed_repository(tmp_path)
    rows = repository.list_news_items(limit=10)

    items = build_news_list_items(rows)
    detail = build_news_detail_view(repository, rows[0])

    assert len(items) == 1
    assert items[0].news_item_id == rows[0]["id"]
    assert detail.news.title == "US CPI cools in March"
    assert detail.analysis is not None
    assert detail.analysis.analysis_card_id.startswith("ac_")
    assert len(detail.evidence_items) == 1
    assert detail.evidence_items[0].evidence_id.startswith("ev_")
