"""Tests that slow or exhausted providers fail fast instead of making the user wait."""

import httpx
import pytest

from app.llm.providers import FallbackChain, LLMError, LLMResult, post_json

URL = "https://example.test/generate"


def make_client(handler) -> httpx.Client:
    """An HTTP client that talks to our fake handler instead of the internet."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_timeout_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("too slow", request=request)

    sleeps = []
    with pytest.raises(LLMError, match="timeout"):
        post_json(make_client(handler), URL, {}, {}, sleeps.append)
    assert len(calls) == 1  # one try only
    assert sleeps == []  # and no waiting


def test_daily_quota_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        message = "Quota exceeded: requests per day limit exceeded"
        return httpx.Response(429, json={"error": {"message": message}})

    sleeps = []
    with pytest.raises(LLMError, match="429"):
        post_json(make_client(handler), URL, {}, {}, sleeps.append)
    assert len(calls) == 1
    assert sleeps == []


def test_short_overload_is_still_retried():
    replies = [503, 503, 200]

    def handler(request):
        if replies.pop(0) == 200:
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(503, json={"error": {"message": "busy"}})

    sleeps = []
    data = post_json(make_client(handler), URL, {}, {}, sleeps.append)
    assert data == {"ok": True}
    assert sleeps == [1.0, 2.0]  # waited briefly twice, then succeeded


class SlowClient:
    provider = "slow"
    model = "m"

    def generate(self, system, user, max_output_tokens=800):
        raise LLMError("timeout: ReadTimeout")


class FastClient:
    provider = "fast"
    model = "m"

    def generate(self, system, user, max_output_tokens=800):
        return LLMResult("ok", "fast", "m", 1, 1, 1)


def test_chain_moves_to_the_backup_after_a_timeout():
    result = FallbackChain([SlowClient(), FastClient()]).generate("sys", "user")
    assert result.provider == "fast"
