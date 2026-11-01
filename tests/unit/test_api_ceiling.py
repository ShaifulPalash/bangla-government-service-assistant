"""Tests for the global ceiling on uncached workflow runs."""

from fastapi.testclient import TestClient

from app.api.guards import RateLimiter
from app.api.main import GRAPH_LIMIT_PER_MINUTE, create_app
from app.api.storage import SQLiteStorage


def make_client(tmp_path, monkeypatch):
    """An isolated app with a temporary database and a fake workflow."""
    storage = SQLiteStorage(tmp_path / "api.sqlite3")
    calls = []

    def fake_ask(graph, question):
        calls.append(question)
        return {
            "decision": "answer",
            "reason": "ok",
            "message": "A fee answer.",
            "language": "en",
            "service": "passport",
            "citations": [],
            "notices": [],
            "top_score": 0.9,
            "provider": "fake",
            "model": "fake-model",
            "path": ["prepare"],
        }

    monkeypatch.setattr("app.api.main.ask", fake_ask)
    app = create_app(
        retriever_factory=lambda: object(),
        workflow_factory=lambda retriever: object(),
        storage_factory=lambda: storage,
    )
    return TestClient(app), calls


def open_visitor_limit(client):
    """The per-visitor limit would stop these tests first, so raise it."""
    client.app.state.rate_limiter = RateLimiter(limit=1000)


def chat(client, question):
    return client.post("/chat", json={"question": question})


def test_the_ceiling_blocks_the_next_uncached_question(tmp_path, monkeypatch):
    client, calls = make_client(tmp_path, monkeypatch)
    with client:
        open_visitor_limit(client)
        responses = [
            chat(client, f"How much is the passport fee, case {number}?")
            for number in range(GRAPH_LIMIT_PER_MINUTE + 1)
        ]
    assert [r.status_code for r in responses[:-1]] == [200] * GRAPH_LIMIT_PER_MINUTE
    assert responses[-1].status_code == 429
    assert int(responses[-1].headers["retry-after"]) >= 1
    assert len(calls) == GRAPH_LIMIT_PER_MINUTE  # the blocked question never ran


def test_cached_questions_are_still_served_when_the_ceiling_is_used_up(tmp_path, monkeypatch):
    client, calls = make_client(tmp_path, monkeypatch)
    with client:
        open_visitor_limit(client)
        client.app.state.graph_limiter = RateLimiter(limit=1)
        first = chat(client, "How much is the passport fee?")
        other = chat(client, "Where is the Dhaka passport office?")
        again = chat(client, "How much is the passport fee?")
    assert first.status_code == 200
    assert other.status_code == 429
    assert again.status_code == 200
    assert again.json()["cached"] is True
    assert len(calls) == 1


def test_repeating_one_question_never_reaches_the_ceiling(tmp_path, monkeypatch):
    client, calls = make_client(tmp_path, monkeypatch)
    with client:
        open_visitor_limit(client)
        client.app.state.graph_limiter = RateLimiter(limit=2)
        statuses = [chat(client, "How much is the passport fee?").status_code for _ in range(20)]
    assert statuses == [200] * 20
    assert len(calls) == 1  # one workflow run, nineteen cache hits
