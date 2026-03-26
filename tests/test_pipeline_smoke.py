from pathlib import Path

from agents.analyst import AnalystAgent
from agents.narrative_manager import NarrativeManagerAgent
from agents.news_sorter import NewsSorterAgent
from pipelines.analyze import analyze_resource_cards
from pipelines.clean import process_raw_items
from pipelines.evidence_extract import extract_evidence_from_analysis
from pipelines.narrative_update import update_from_evidence
from utils.io import write_json, write_model, write_models


def test_pipeline_smoke(tmp_path: Path) -> None:
    raw_items = [
        {
            "title": "US CPI cools",
            "summary": "Inflation is slowing.",
            "source": "example",
            "url": "https://example.com",
            "region": ["US"],
            "theme": ["inflation"],
            "importance_score": 0.9,
            "structural_score": 0.8,
            "verifiability_score": 0.9,
        }
    ]

    sorter = NewsSorterAgent()
    analyst = AnalystAgent()
    narrative = NarrativeManagerAgent()

    resource_cards = process_raw_items(raw_items, sorter)
    analysis_cards = analyze_resource_cards(resource_cards, analyst)
    evidence_list = extract_evidence_from_analysis(
        analysis_cards,
        analyst,
        context={"target_main_narrative_id": "main_default"},
    )
    state = update_from_evidence(evidence_list, analysis_cards, narrative)

    write_models(tmp_path / "resource_cards", resource_cards)
    write_models(tmp_path / "analysis_archive", analysis_cards)
    write_models(tmp_path / "evidence", evidence_list)
    write_model(tmp_path / "main_narrative_state" / "main_default.json", state["main_narrative"])
    write_models(tmp_path / "branch_narrative_state", state["branches"])
    write_models(tmp_path / "narrative_commits", state["commits"])
    write_models(tmp_path / "alerts", state["alerts"])
    write_models(tmp_path / "scenarios", state["scenarios"])
    write_json(tmp_path / "raw_inputs" / "raw_news.json", raw_items)

    assert len(resource_cards) == 1
    assert len(analysis_cards) == 1
    assert len(evidence_list) == 1
    assert len(state["commits"]) == 1
    assert (tmp_path / "resource_cards").exists()
    assert (tmp_path / "narrative_commits" / f"{state['commits'][0].id}.json").exists()
