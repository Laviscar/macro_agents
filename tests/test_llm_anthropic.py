import json
import pytest
from llm.anthropic_client import AnthropicClient
from llm.base import LLMError, LLMMessage
from llm.config import LLMConfig


def _cfg(api_key="k"):
    return LLMConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        api_key=api_key,
        base_url="https://api.anthropic.com/v1",
    )


def test_complete_builds_messages_request_and_parses():
    captured = {}

    def fake_transport(url, headers, body, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json.loads(body.decode("utf-8"))
        return {
            "content": [{"type": "text", "text": "claude says hi"}],
            "usage": {"input_tokens": 5, "output_tokens": 9},
        }

    client = AnthropicClient(_cfg(), transport=fake_transport)
    resp = client.complete(
        [LLMMessage(role="system", content="be terse"), LLMMessage(role="user", content="hi")],
        max_tokens=128,
    )

    assert resp.text == "claude says hi"
    assert resp.input_tokens == 5
    assert resp.output_tokens == 9
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "k"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["body"]["system"] == "be terse"
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["body"]["max_tokens"] == 128


def test_missing_key_raises():
    client = AnthropicClient(_cfg(api_key=None), transport=lambda *a: {})
    with pytest.raises(LLMError):
        client.complete([LLMMessage(role="user", content="hi")])


def test_bad_shape_raises():
    client = AnthropicClient(_cfg(), transport=lambda *a: {"content": []})
    with pytest.raises(LLMError):
        client.complete([LLMMessage(role="user", content="hi")])
