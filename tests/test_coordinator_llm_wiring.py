from harness.coordinator import HarnessCoordinator


def test_coordinator_analyst_has_no_llm_client_when_env_unset(tmp_path, monkeypatch):
    for var in ["OPENAI_API_KEY", "MINIMAX_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY"]:
        monkeypatch.delenv(var, raising=False)
    coord = HarnessCoordinator(db_path=tmp_path / "t.sqlite3", storage_root=tmp_path / "s")
    assert coord._analyst._llm_client is None


def test_coordinator_builds_llm_client_when_env_set(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-for-test")
    coord = HarnessCoordinator(db_path=tmp_path / "t.sqlite3", storage_root=tmp_path / "s")
    assert coord._analyst._llm_client is not None
