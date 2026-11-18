"""A Groq reply with no text must say why."""

import httpx
import pytest

from app.llm.providers import GroqClient, LLMError


def test_an_empty_groq_reply_reports_response_metadata():
    def handler(request):
        body = {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "refusal": None,
                        "tool_calls": None,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "completion_tokens": 362,
                "completion_tokens_details": {"reasoning_tokens": 21},
            },
        }
        return httpx.Response(200, json=body)

    client = GroqClient("key", "model", client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(
        LLMError,
        match=(
            r"finish reason: stop, output tokens: 362, reasoning tokens: 21, "
            r"message fields: content,refusal,tool_calls, refusal: False, tool calls: 0"
        ),
    ):
        client.generate("system", "user")
