from llm.config import LLMConfig, load_llm_config


def test_defaults_to_openai_when_unset():
    cfg = load_llm_config(env={})
    assert cfg.provider == "openai"
    assert cfg.base_url == "https://api.openai.com/v1"
    assert cfg.api_key is None
    assert cfg.is_configured is False


def test_reads_openai_key_from_default_env():
    cfg = load_llm_config(env={"OPENAI_API_KEY": "sk-test"})
    assert cfg.api_key == "sk-test"
    assert cfg.is_configured is True


def test_provider_specific_key_env():
    cfg = load_llm_config(env={"LLM_PROVIDER": "minimax", "MINIMAX_API_KEY": "mm-test"})
    assert cfg.provider == "minimax"
    assert cfg.base_url == "https://api.minimax.chat/v1"
    assert cfg.api_key == "mm-test"


def test_custom_key_env_name_and_overrides():
    cfg = load_llm_config(env={
        "LLM_PROVIDER": "openai",
        "LLM_API_KEY_ENV": "MY_KEY",
        "MY_KEY": "abc",
        "LLM_MODEL": "gpt-4o",
        "LLM_BASE_URL": "https://proxy.local/v1",
    })
    assert cfg.api_key == "abc"
    assert cfg.model == "gpt-4o"
    assert cfg.base_url == "https://proxy.local/v1"


def test_anthropic_defaults():
    cfg = load_llm_config(env={"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k"})
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.base_url == "https://api.anthropic.com/v1"


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
