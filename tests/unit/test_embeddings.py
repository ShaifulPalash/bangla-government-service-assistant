import math

import httpx
import pytest

from app.indexing.embeddings import (
    BATCH_SIZE,
    DIMENSIONS,
    MAX_RETRIES,
    Embedder,
    EmbeddingError,
    document_text,
    query_text,
)


def vector_for(text: str) -> list[float]:
    """A fake vector whose first number is the last word of the text, as a number."""
    number = float(text.split()[-1]) if text.split()[-1].isdigit() else 0.0
    return [number] + [0.0] * (DIMENSIONS - 1)


class FakeServer:
    """Pretends to be Google. Records every call, and can fail on demand."""

    def __init__(self, failures=None, wrong_count=False):
        self.calls = []  # the texts of every request received
        self.failures = list(failures or [])  # status codes to return before succeeding
        self.wrong_count = wrong_count

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import json

        texts = [r["content"]["parts"][0]["text"] for r in json.loads(request.content)["requests"]]
        self.calls.append(texts)
        if self.failures:
            status = self.failures.pop(0)
            return httpx.Response(status, json={"error": {"message": "fake failure"}})
        vectors = [{"values": vector_for(text)} for text in texts]
        if self.wrong_count:
            vectors = vectors[:1]
        return httpx.Response(200, json={"embeddings": vectors})


def make_embedder(server, cache_path=None, sleeps=None):
    client = httpx.Client(transport=httpx.MockTransport(server))
    sleeps = sleeps if sleeps is not None else []
    return Embedder("fake-key", cache_path=cache_path, client=client, sleep=sleeps.append, pause=0)


def test_prefix_helpers_follow_the_model_format():
    assert document_text(None, "x") == "title: none | text: x"
    assert document_text("Fees", "x") == "title: Fees | text: x"
    assert query_text("q") == "task: search result | query: q"


def test_embeds_in_input_order_and_in_batches():
    server = FakeServer()
    texts = [f"text {i}" for i in range(25)]
    vectors = make_embedder(server).embed(texts)
    assert [vector[0] for vector in vectors] == [float(i) for i in range(25)]
    assert len(server.calls) == math.ceil(25 / BATCH_SIZE)


def test_repeated_texts_are_not_sent_again():
    server = FakeServer()
    embedder = make_embedder(server)
    embedder.embed(["text 1", "text 2"])
    embedder.embed(["text 1", "text 2"])
    assert len(server.calls) == 1
    assert embedder.stats["from_cache"] == 2


def test_duplicate_texts_in_one_call_are_sent_once():
    server = FakeServer()
    vectors = make_embedder(server).embed(["text 1", "text 1", "text 2"])
    assert sum(len(call) for call in server.calls) == 2
    assert vectors[0] == vectors[1]


def test_cache_survives_a_restart(tmp_path):
    cache = tmp_path / "cache.jsonl"
    first = FakeServer()
    make_embedder(first, cache_path=cache).embed(["text 1", "text 2"])
    second = FakeServer()
    vectors = make_embedder(second, cache_path=cache).embed(["text 1", "text 2"])
    assert second.calls == []
    assert vectors[1][0] == 2.0


def test_retries_after_a_rate_limit_and_waits():
    server = FakeServer(failures=[429])
    sleeps = []
    vectors = make_embedder(server, sleeps=sleeps).embed(["text 1"])
    assert vectors[0][0] == 1.0
    assert len(server.calls) == 2
    assert sleeps == [5]


def test_gives_up_after_too_many_temporary_failures():
    server = FakeServer(failures=[503] * (MAX_RETRIES + 1))
    with pytest.raises(EmbeddingError, match="gave up"):
        make_embedder(server).embed(["text 1"])
    assert len(server.calls) == MAX_RETRIES + 1


def test_client_errors_are_not_retried():
    server = FakeServer(failures=[400])
    with pytest.raises(EmbeddingError, match="HTTP 400"):
        make_embedder(server).embed(["text 1"])
    assert len(server.calls) == 1


def test_wrong_number_of_vectors_is_an_error():
    server = FakeServer(wrong_count=True)
    with pytest.raises(EmbeddingError, match="expected 2 vectors"):
        make_embedder(server).embed(["text 1", "text 2"])
