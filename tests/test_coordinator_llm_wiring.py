from harness.coordinator import HarnessCoordinator, TaskInput


def test_coordinator_analyst_has_no_llm_client_when_env_unset(tmp_path, monkeypatch):
    for var in ["OPENAI_API_KEY", "MINIMAX_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY"]:
        monkeypatch.delenv(var, raising=False)
    coord = HarnessCoordinator(db_path=tmp_path / "t.sqlite3", storage_root=tmp_path / "s")
    assert coord._analyst._llm_client is None
    assert coord._narrative_manager._llm_client is None
    assert coord._token_meter is None


def test_coordinator_builds_metered_client_when_env_set(tmp_path, monkeypatch):
    from llm.metering import MeteredLLMClient, TokenMeter
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-for-test")
    coord = HarnessCoordinator(db_path=tmp_path / "t.sqlite3", storage_root=tmp_path / "s")
    assert isinstance(coord._token_meter, TokenMeter)
    assert isinstance(coord._analyst._llm_client, MeteredLLMClient)
    assert isinstance(coord._narrative_manager._llm_client, MeteredLLMClient)


def test_task_input_token_budget_defaults_zero():
    ti = TaskInput(news_item_ids=[1])
    assert ti.token_budget == 0
