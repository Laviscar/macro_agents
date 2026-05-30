from llm.base import LLMMessage, LLMResponse
from llm.fake import FakeLLMClient
from llm.metering import MeteredLLMClient, TokenMeter


def test_token_meter_add_total_drain_reset():
    m = TokenMeter()
    assert m.total == 0
    m.add(10)
    m.add(5)
    assert m.total == 15
    drained = m.drain()
    assert drained == 15
    assert m.total == 0  # drain resets running total
    m.add(3)
    m.reset()
    assert m.total == 0


def test_metered_client_accumulates_tokens_and_passes_response_through():
    import json
    base = FakeLLMClient(responses=[json.dumps({"ok": True})])
    meter = TokenMeter()
    client = MeteredLLMClient(base, meter)
    resp = client.complete([LLMMessage(role="user", content="hi")])
    assert isinstance(resp, LLMResponse)
    assert resp.text == json.dumps({"ok": True})
    assert meter.total == 30


def test_metered_client_accumulates_across_calls():
    base = FakeLLMClient(responses=["a", "b"])
    meter = TokenMeter()
    client = MeteredLLMClient(base, meter)
    client.complete([LLMMessage(role="user", content="x")])
    client.complete([LLMMessage(role="user", content="y")])
    assert meter.total == 60  # 2 calls x (10+20)


def test_metered_client_satisfies_llm_client_protocol():
    from llm.base import LLMClient
    client = MeteredLLMClient(FakeLLMClient(), TokenMeter())
    assert isinstance(client, LLMClient)
