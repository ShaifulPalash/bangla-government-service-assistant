"""Tests that an unreadable reply moves on to the next provider."""

import pytest

from app.llm.prompts import parse_answer
from app.llm.providers import FallbackChain, LLMError, LLMResult

GOOD = '{"can_answer": true, "answer": "ok", "sources": [1]}'


class Client:
    model = "m"

    def __init__(self, provider: str, text: str) -> None:
        self.provider = provider
        self.text = text

    def generate(self, system, user, max_output_tokens=800):
        return LLMResult(self.text, self.provider, "m", 1, 1, 1)


def readable(text: str) -> bool:
    return parse_answer(text).can_answer is not None


def test_unreadable_reply_moves_on_to_the_next_provider():
    chain = FallbackChain([Client("first", "not json"), Client("second", GOOD)])
    assert chain.generate("s", "u", accept=readable).provider == "second"


def test_without_accept_the_first_reply_is_used():
    chain = FallbackChain([Client("first", "not json"), Client("second", GOOD)])
    assert chain.generate("s", "u").provider == "first"


def test_all_unreadable_replies_raise_an_error():
    chain = FallbackChain([Client("first", "no"), Client("second", "also no")])
    with pytest.raises(LLMError, match="unreadable"):
        chain.generate("s", "u", accept=readable)


def test_parse_answer_allows_raw_line_breaks_in_the_text():
    raw = '{"can_answer": true, "answer": "line one\nline two", "sources": [1]}'
    parsed = parse_answer(raw)
    assert parsed.can_answer is True
    assert "line two" in parsed.answer


def test_parse_answer_reads_true_written_as_text():
    parsed = parse_answer('{"can_answer": "true", "answer": "ok", "sources": [1]}')
    assert parsed.can_answer is True
