"""Tests for the Streamlit page's API client, using a fake server."""

import json

import httpx
import pytest
from ui.api_client import ApiClient, ApiError


def client_for(handler, sleeps=None) -> ApiClient:
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    wait = sleeps.append if sleeps is not None else (lambda seconds: None)
    return ApiClient("http://test", client=http, sleep=wait)


def body(decision="answer", **extra) -> dict:
    return {
        "request_id": "r1",
        "decision": decision,
        "reason": "ok",
        "message": "The fee is TK 4,025.",
        "language": "en",
        **extra,
    }


def test_a_normal_reply_becomes_an_answer():
    reply = body(citations=[{"title": "Fees"}], cached=True, took_ms=120, provider="groq")
    answer = client_for(lambda request: httpx.Response(200, json=reply)).ask("fee?")
    assert answer.decision == "answer"
    assert answer.citations == [{"title": "Fees"}]
    assert (answer.cached, answer.took_ms, answer.provider) == (True, 120, "groq")


def test_the_question_is_sent_to_chat():
    seen = []

    def handler(request):
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json=body())

    client_for(handler).ask("How much is the fee?")
    assert seen == [("/chat", {"question": "How much is the fee?"})]


def test_a_503_with_a_normal_body_is_an_unavailable_answer():
    reply = body("unavailable", reason="llm_unavailable")
    answer = client_for(lambda request: httpx.Response(503, json=reply)).ask("fee?")
    assert (answer.decision, answer.reason) == ("unavailable", "llm_unavailable")


def test_too_many_requests_is_busy_with_the_wait_time():
    response = httpx.Response(429, headers={"Retry-After": "42"}, json={"error": "slow down"})
    with pytest.raises(ApiError) as caught:
        client_for(lambda request: response).ask("fee?")
    assert (caught.value.kind, caught.value.retry_after) == ("busy", 42)


def test_an_invalid_question_is_reported():
    with pytest.raises(ApiError) as caught:
        client_for(lambda request: httpx.Response(422, json={})).ask("x")
    assert caught.value.kind == "invalid"


def test_a_timeout_is_reported():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ApiError) as caught:
        client_for(handler).ask("fee?")
    assert caught.value.kind == "timeout"


def test_a_connection_failure_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(ApiError) as caught:
        client_for(handler).ask("fee?")
    assert caught.value.kind == "unavailable"


def test_a_reply_that_is_not_json_is_unavailable():
    with pytest.raises(ApiError) as caught:
        client_for(lambda request: httpx.Response(200, text="<html>")).ask("fee?")
    assert caught.value.kind == "unavailable"


def test_wake_up_keeps_trying_until_the_server_answers():
    replies = [503, 503, 200]
    sleeps: list[float] = []
    client = client_for(lambda request: httpx.Response(replies.pop(0)), sleeps)
    assert client.wake_up(attempts=5, pause=10) is True
    assert sleeps == [10, 10]


def test_wake_up_gives_up_after_the_attempts():
    sleeps: list[float] = []
    client = client_for(lambda request: httpx.Response(503), sleeps)
    assert client.wake_up(attempts=3, pause=5) is False
    assert sleeps == [5, 5]  # no waiting after the last attempt


def test_feedback_is_sent_with_a_valid_category():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "accepted"})

    assert client_for(handler).send_feedback("r1", -1, "outdated") is True
    assert seen == [{"request_id": "r1", "rating": -1, "category": "outdated"}]


def test_an_unknown_category_is_dropped():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "accepted"})

    client_for(handler).send_feedback("r1", 1, "rude")
    assert "category" not in seen[0]


def test_a_failed_feedback_call_never_raises():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    assert client_for(handler).send_feedback("r1", 1) is False
    assert client_for(lambda request: httpx.Response(404)).send_feedback("r1", 1) is False
