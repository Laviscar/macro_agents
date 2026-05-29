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
