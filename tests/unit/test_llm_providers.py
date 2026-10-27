import json

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.llm.providers import (
    MAX_RETRIES,
    FallbackChain,
    GeminiClient,
    GroqClient,
    LLMError,
    LLMResult,
    build_chain,
)


class FakeServer:
    """Stands in for the provider. Replies come from a list; the last one repeats."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply


def make_client(server: FakeServer) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(server))


def gemini_ok(text="the answer"):
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30},
        },
    )


def groq_ok(text="the answer"):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 25},
        },
    )


def gemini(server, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return GeminiClient("key-g", "gemini-3.8-flash", make_client(server), sleeps.append)


def groq(server, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return GroqClient("key-q", "openai/gpt-oss-120b", make_client(server), sleeps.append)


def test_gemini_request_follows_the_documented_shape_and_result_is_read():
    server = FakeServer(gemini_ok("hello"))
    result = gemini(server).generate("be careful", "question?", max_output_tokens=500)
    request = server.requests[0]
    body = json.loads(request.content)
    assert str(request.url).endswith("/models/gemini-3.8-flash:generateContent")
    assert request.headers["x-goog-api-key"] == "key-g"
    assert body["system_instruction"]["parts"][0]["text"] == "be careful"
    assert body["contents"][0]["parts"][0]["text"] == "question?"
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert body["generationConfig"]["maxOutputTokens"] == 500
    assert "temperature" not in body["generationConfig"]
    assert (result.text, result.provider, result.prompt_tokens, result.output_tokens) == (
        "hello",
        "gemini",
        120,
        30,
    )


def test_a_temporary_failure_is_retried_after_a_short_wait():
    server = FakeServer(httpx.Response(503, json={"error": {"message": "busy"}}), gemini_ok())
    sleeps: list[float] = []
    assert gemini(server, sleeps).generate("s", "u").text == "the answer"
    assert len(server.requests) == 2
    assert sleeps == [1.0]


def test_it_gives_up_after_the_allowed_retries():
    server = FakeServer(httpx.Response(500, json={"error": {"message": "down"}}))
    sleeps: list[float] = []
    with pytest.raises(LLMError, match="gave up"):
        gemini(server, sleeps).generate("s", "u")
    assert len(server.requests) == MAX_RETRIES + 1


def test_a_bad_request_is_not_retried():
    server = FakeServer(httpx.Response(400, json={"error": {"message": "bad field"}}))
    with pytest.raises(LLMError, match="HTTP 400: bad field"):
        gemini(server).generate("s", "u")
    assert len(server.requests) == 1


def test_a_long_retry_after_hands_over_to_the_next_provider_without_waiting():
    server = FakeServer(httpx.Response(429, headers={"retry-after": "40"}, json={}))
    sleeps: list[float] = []
    with pytest.raises(LLMError):
        gemini(server, sleeps).generate("s", "u")
    assert sleeps == []
    assert len(server.requests) == 1


def test_a_blocked_or_empty_gemini_answer_is_an_error():
    blocked = FakeServer(httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(LLMError, match="blocked"):
        gemini(blocked).generate("s", "u")
    empty = FakeServer(gemini_ok("   "))
    with pytest.raises(LLMError, match="empty"):
        gemini(empty).generate("s", "u")


def test_groq_request_and_result():
    server = FakeServer(groq_ok("hi"))
    result = groq(server).generate("sys", "usr", max_output_tokens=300)
    request = server.requests[0]
    body = json.loads(request.content)
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer key-q"
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["max_completion_tokens"] == 300
    assert "reasoning_effort" not in body
    assert (result.text, result.provider, result.output_tokens) == ("hi", "groq", 25)


def test_groq_can_be_asked_for_low_reasoning():
    server = FakeServer(groq_ok())
    client = GroqClient("k", "m", make_client(server), lambda s: None, reasoning_effort="low")
    client.generate("s", "u")
    assert json.loads(server.requests[0].content)["reasoning_effort"] == "low"


def test_chain_uses_the_backup_when_the_first_provider_fails():
    first = FakeServer(httpx.Response(400, json={"error": {"message": "nope"}}))
    second = FakeServer(groq_ok("from groq"))
    result = FallbackChain([gemini(first), groq(second)]).generate("s", "u")
    assert (result.provider, result.text) == ("groq", "from groq")


def test_chain_does_not_call_the_backup_when_the_first_works():
    first, second = FakeServer(gemini_ok()), FakeServer(groq_ok())
    FallbackChain([gemini(first), groq(second)]).generate("s", "u")
    assert second.requests == []


def test_chain_reports_every_failure_when_all_fail():
    bad = httpx.Response(400, json={"error": {"message": "nope"}})
    chain = FallbackChain([gemini(FakeServer(bad)), groq(FakeServer(bad))])
    with pytest.raises(LLMError) as info:
        chain.generate("s", "u")
    message = str(info.value)
    assert "gemini/gemini-3.8-flash" in message and "groq/openai/gpt-oss-120b" in message


def test_build_chain_follows_the_configured_keys():
    both = Settings(_env_file=None, gemini_api_key=SecretStr("g"), groq_api_key=SecretStr("q"))
    assert [client.provider for client in build_chain(both).clients] == ["groq", "gemini"]
    only_groq = Settings(_env_file=None, groq_api_key=SecretStr("q"))
    assert [client.provider for client in build_chain(only_groq).clients] == ["groq"]
    with pytest.raises(LLMError, match="no language-model key"):
        build_chain(Settings(_env_file=None))


def test_result_object_holds_what_the_workflow_needs():
    result = LLMResult("t", "gemini", "m", 1, 2, 3)
    assert result.latency_ms == 3
