from __future__ import annotations

from pathlib import Path

from agents.analyst import AnalystAgent
from agents.narrative_manager import NarrativeManagerAgent
from agents.news_sorter import NewsSorterAgent
from pipelines.analyze import analyze_resource_cards
from pipelines.clean import process_raw_items
from pipelines.evidence_extract import extract_evidence_from_analysis
from pipelines.ingest import load_raw_news
from pipelines.narrative_update import update_from_evidence
from utils.io import clear_json_files, write_json, write_model, write_models
from utils.knowledge_loader import KnowledgeLoader


PROJECT_ROOT = Path(__file__).resolve().parent
EXAMPLES_ROOT = PROJECT_ROOT / "examples"
STORAGE_ROOT = PROJECT_ROOT / "storage"


def run_demo(
    sample_news_path: Path | None = None,
    storage_root: Path | None = None,
) -> dict:
    input_path = sample_news_path or EXAMPLES_ROOT / "sample_news.json"
    output_root = storage_root or STORAGE_ROOT

    raw_items = load_raw_news(str(input_path))
    knowledge_loader = KnowledgeLoader(str(PROJECT_ROOT / "knowledge" / "registry.yaml"))

    sorter = NewsSorterAgent()
    analyst = AnalystAgent(
        knowledge_context=knowledge_loader.load_context(
            "analyst",
            tasks=["analyze_event", "extract_evidence"],
        )
    )
    narrative = NarrativeManagerAgent(
        knowledge_context=knowledge_loader.load_context(
            "narrative_manager",
            tasks=["record_commit"],
        )
    )

    resource_cards = process_raw_items(raw_items, sorter)
    analysis_cards = analyze_resource_cards(resource_cards, analyst)
    evidence_list = extract_evidence_from_analysis(
        analysis_cards,
        analyst,
        context={"target_main_narrative_id": "main_default"},
    )
    state = update_from_evidence(evidence_list, analysis_cards, narrative)

    clear_json_files(output_root / "raw_inputs")
    clear_json_files(output_root / "resource_cards")
    clear_json_files(output_root / "analysis_archive")
    clear_json_files(output_root / "evidence")
    clear_json_files(output_root / "main_narrative_state")
    clear_json_files(output_root / "branch_narrative_state")
    clear_json_files(output_root / "narrative_commits")
    clear_json_files(output_root / "scenarios")
    clear_json_files(output_root / "alerts")

    write_json(output_root / "raw_inputs" / "sample_news.json", raw_items)
    write_models(output_root / "resource_cards", resource_cards)
    write_models(output_root / "analysis_archive", analysis_cards)
    write_models(output_root / "evidence", evidence_list)
    write_model(
        output_root / "main_narrative_state" / f"{state['main_narrative'].id}.json",
        state["main_narrative"],
    )
    write_models(output_root / "branch_narrative_state", state["branches"])
    write_models(output_root / "narrative_commits", state["commits"])
    write_models(output_root / "scenarios", state["scenarios"])

    if state["alerts"]:
        write_models(output_root / "alerts", state["alerts"])
    else:
        write_json(
            output_root / "alerts" / "_status.json",
            {
                "status": "no_alert",
                "message": "No challenge alert generated for this demo run.",
            },
        )

    return {
        "input_path": str(input_path),
        "storage_root": str(output_root),
        "resource_cards": resource_cards,
        "analysis_cards": analysis_cards,
        "evidence_list": evidence_list,
        "state": state,
        "knowledge": {
            "analyst": {
                task: [doc["id"] for doc in docs]
                for task, docs in analyst.last_knowledge_docs.items()
            },
            "narrative_manager": {
                task: [doc["id"] for doc in docs]
                for task, docs in narrative.last_knowledge_docs.items()
            },
        },
    }


def main() -> None:
    from utils.dotenv import load_dotenv

    load_dotenv()  # populate os.environ from .env (shell exports still win)
    result = run_demo()
    state = result["state"]

    print(f"Loaded sample input: {result['input_path']}")
    print(f"ResourceCards: {len(result['resource_cards'])}")
    print(f"AnalysisCards: {len(result['analysis_cards'])}")
    print(f"Evidence: {len(result['evidence_list'])}")
    print(f"Branches: {len(state['branches'])}")
    print(f"NarrativeCommits: {len(state['commits'])}")
    print(f"Scenarios: {len(state['scenarios'])}")
    if state["alerts"]:
        print(f"Alerts: {len(state['alerts'])}")
    else:
        print("Alerts: 0 (written as storage/alerts/_status.json)")
    print(f"Outputs written to: {result['storage_root']}")


if __name__ == "__main__":
    main()
