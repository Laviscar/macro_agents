import pytest
from llm.anthropic_client import AnthropicClient
from llm.base import LLMMessage
from llm.config import LLMConfig
from llm.factory import build_llm_client
from llm.fake import FakeLLMClient
from llm.openai_compatible import OpenAICompatibleClient


def _cfg(provider, api_key="k"):
    return LLMConfig(provider=provider, model="m", api_key=api_key, base_url="https://x/v1")


def test_unconfigured_returns_none():
    assert build_llm_client(_cfg("openai", api_key=None)) is None


def test_openai_provider_builds_openai_compatible():
    assert isinstance(build_llm_client(_cfg("openai")), OpenAICompatibleClient)


def test_minimax_provider_builds_openai_compatible():
    assert isinstance(build_llm_client(_cfg("minimax")), OpenAICompatibleClient)


def test_anthropic_provider_builds_anthropic():
    assert isinstance(build_llm_client(_cfg("anthropic")), AnthropicClient)


def test_unknown_provider_returns_none():
    assert build_llm_client(_cfg("unknownvendor")) is None


def test_fake_client_returns_canned_and_records_calls():
    fake = FakeLLMClient(responses=["first", "second"])
    r1 = fake.complete([LLMMessage(role="user", content="a")])
    r2 = fake.complete([LLMMessage(role="user", content="b")])
    assert (r1.text, r2.text) == ("first", "second")
    assert len(fake.calls) == 2


def test_fake_client_raises_configured_error():
    from llm.base import LLMError
    fake = FakeLLMClient(error=LLMError("boom"))
    with pytest.raises(LLMError):
        fake.complete([LLMMessage(role="user", content="a")])
