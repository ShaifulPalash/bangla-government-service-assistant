from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.main import EXCERPT_CHARS, SEARCH_MODE, create_app
from app.indexing.embeddings import EmbeddingError


def make_result(i: int, text: str = "some passage text") -> dict:
    return {
        "chunk_id": f"ppt-002-p000-c0{i}",
        "doc_id": "ppt-002",
        "title": "E-Passport Fees",
        "url": "https://example.gov.bd/fees",
        "service": "passport",
        "language": "en",
        "publisher": "DIP",
        "page": None,
        "last_updated_date": "",
        "verified_date": "2026-10-15",
        "extraction": "web_text",
        "text": text,
        "score": 0.9 - i / 10,
        "meaning_score": 0.9 - i / 10,
        "word_score": None,
        "meaning_rank": i + 1,
        "word_rank": None,
    }


class FakeRetriever:
    def __init__(self, results=None, error=None):
        self.results = results if results is not None else [make_result(0), make_result(1)]
        self.error = error
        self.calls = []
        self.collection = SimpleNamespace(count=lambda: 187)

    def retrieve(self, question, k, mode, service):
        self.calls.append({"question": question, "k": k, "mode": mode, "service": service})
        if self.error:
            raise self.error
        return self.results[:k]


def client_for(retriever=None, factory_error=None):
    def factory():
        if factory_error:
            raise factory_error
        return retriever or FakeRetriever()

    return TestClient(create_app(factory))


def test_health_reports_ready_with_chunk_count():
    with client_for() as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "chunks": 187,
        "embedding_model": "gemini-embedding-2",
    }


def test_health_is_503_when_the_index_is_missing_but_the_app_still_starts():
    with client_for(factory_error=FileNotFoundError("Vector index not found")) as client:
        response = client.get("/health")
        search = client.get("/search", params={"q": "passport fee"})
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert "Vector index not found" in response.json()["detail"]
    assert search.status_code == 503


def test_health_is_503_when_the_api_key_is_missing():
    with client_for(factory_error=RuntimeError("GEMINI_API_KEY is not set")) as client:
        assert client.get("/health").status_code == 503


def test_search_returns_hits_with_citation_details():
    retriever = FakeRetriever()
    with client_for(retriever) as client:
        response = client.get("/search", params={"q": "passport fee", "k": 2})
    body = response.json()
    assert response.status_code == 200
    assert body["question"] == "passport fee"
    assert len(body["hits"]) == 2
    first = body["hits"][0]
    assert first["doc_id"] == "ppt-002"
    assert first["url"] == "https://example.gov.bd/fees"
    assert first["last_updated_date"] is None  # an empty date becomes null
    assert first["page"] is None
    assert body["took_ms"] >= 0
    assert retriever.calls == [
        {"question": "passport fee", "k": 2, "mode": SEARCH_MODE, "service": None}
    ]


def test_search_passes_the_service_filter_on():
    retriever = FakeRetriever()
    with client_for(retriever) as client:
        client.get("/search", params={"q": "lost card", "service": "nid"})
    assert retriever.calls[0]["service"] == "nid"


def test_long_passages_are_shortened_to_an_excerpt():
    long_text = "word " * 200
    with client_for(FakeRetriever([make_result(0, long_text)])) as client:
        hit = client.get("/search", params={"q": "fee"}).json()["hits"][0]
    assert len(hit["excerpt"]) <= EXCERPT_CHARS + 3
    assert hit["excerpt"].endswith("...")


@pytest.mark.parametrize(
    "params",
    [
        {},  # no question
        {"q": "a"},  # too short
        {"q": "x" * 301},  # too long
        {"q": "fee", "k": 0},
        {"q": "fee", "k": 9},
        {"q": "fee", "service": "tax"},
    ],
)
def test_bad_input_is_rejected_with_422(params):
    with client_for() as client:
        assert client.get("/search", params=params).status_code == 422


def test_embedding_failure_becomes_a_502_not_a_crash():
    with client_for(FakeRetriever(error=EmbeddingError("HTTP 429: quota"))) as client:
        response = client.get("/search", params={"q": "passport fee"})
    assert response.status_code == 502
    assert "unavailable" in response.json()["error"]


def test_the_base_address_redirects_to_the_documentation():
    with client_for() as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
