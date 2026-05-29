import json
import pytest
from llm.base import LLMError, LLMMessage
from llm.config import LLMConfig
from llm.openai_compatible import OpenAICompatibleClient


def _cfg(api_key="sk-test"):
    return LLMConfig(
        provider="openai",
        model="gpt-4o-mini",
        api_key=api_key,
        base_url="https://api.openai.com/v1",
    )


def test_complete_builds_request_and_parses_response():
    captured = {}

    def fake_transport(url, headers, body, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json.loads(body.decode("utf-8"))
        return {
            "choices": [{"message": {"content": "hello world"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        }

    client = OpenAICompatibleClient(_cfg(), transport=fake_transport)
    resp = client.complete([LLMMessage(role="user", content="hi")], max_tokens=256)

    assert resp.text == "hello world"
    assert resp.input_tokens == 11
    assert resp.output_tokens == 7
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["body"]["model"] == "gpt-4o-mini"
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["body"]["max_tokens"] == 256


def test_missing_api_key_raises_llm_error():
    client = OpenAICompatibleClient(_cfg(api_key=None), transport=lambda *a: {})
    with pytest.raises(LLMError):
        client.complete([LLMMessage(role="user", content="hi")])


def test_transport_exception_wrapped_as_llm_error():
    def boom(url, headers, body, timeout):
        raise OSError("connection refused")

    client = OpenAICompatibleClient(_cfg(), transport=boom)
    with pytest.raises(LLMError):
        client.complete([LLMMessage(role="user", content="hi")])


def test_unexpected_response_shape_raises_llm_error():
    client = OpenAICompatibleClient(_cfg(), transport=lambda *a: {"nope": True})
    with pytest.raises(LLMError):
        client.complete([LLMMessage(role="user", content="hi")])
