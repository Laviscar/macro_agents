from pathlib import Path

import demo_runner
from demo_runner import run_demo


def test_demo_default_output_is_sandbox_not_production() -> None:
    # Foundation contract: demo_runner clears its output each run, so its default
    # output must be an isolated sandbox, never the production storage/ that
    # run_harness accumulates and the UI reads.
    assert demo_runner.DEMO_STORAGE_ROOT == demo_runner.STORAGE_ROOT / "demo"
    assert demo_runner.DEMO_STORAGE_ROOT != demo_runner.STORAGE_ROOT


def test_demo_runner_writes_storage_outputs(tmp_path: Path) -> None:
    result = run_demo(
        sample_news_path=Path("examples/sample_news.json"),
        storage_root=tmp_path,
    )

    assert len(result["resource_cards"]) == 1
    assert len(result["analysis_cards"]) == 1
    assert len(result["evidence_list"]) == 1
    assert len(result["state"]["commits"]) == 1
    assert list((tmp_path / "resource_cards").glob("*.json"))
    assert list((tmp_path / "analysis_archive").glob("*.json"))
    assert list((tmp_path / "evidence").glob("*.json"))
    assert list((tmp_path / "main_narrative_state").glob("*.json"))
    assert list((tmp_path / "narrative_commits").glob("*.json"))
    assert list((tmp_path / "alerts").glob("*.json"))
    assert (tmp_path / "branch_narrative_state").exists()
    assert (tmp_path / "scenarios").exists()
