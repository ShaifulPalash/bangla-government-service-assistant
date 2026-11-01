"""Tests for the chat and feedback API endpoints."""

import sqlite3

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.storage import SQLiteStorage


def answer_result(
    *,
    decision="answer",
    reason="ok",
    message="The passport fee depends on the service selected.",
    notices=None,
):
    """Build a representative workflow result without calling a real model."""
    return {
        "decision": decision,
        "reason": reason,
        "message": message,
        "language": "en",
        "service": "passport",
        "citations": [
            {
                "doc_id": "ppt-002",
                "title": "E-Passport Fees",
                "url": "https://example.gov.bd/fees",
                "numbers": [1],
            }
        ],
        "notices": notices or [],
        "top_score": 0.9,
        "provider": "fake",
        "model": "fake-model",
        "path": ["prepare", "classify", "retrieve", "answer", "respond"],
    }


def make_client(tmp_path, monkeypatch, result=None):
    """Create an isolated app with a temporary database and fake workflow."""
    storage = SQLiteStorage(tmp_path / "api.sqlite3")
    calls = []

    def fake_ask(graph, question):
        calls.append(question)
        return dict(result or answer_result())

    monkeypatch.setattr("app.api.main.ask", fake_ask)

    app = create_app(
        retriever_factory=lambda: object(),
        workflow_factory=lambda retriever: object(),
        storage_factory=lambda: storage,
    )
    return TestClient(app), storage, calls


def test_chat_returns_answer_and_persisted_request_id(tmp_path, monkeypatch):
    client, storage, calls = make_client(tmp_path, monkeypatch)

    with client:
        response = client.post(
            "/chat",
            json={"question": "How much is the passport fee?"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "answer"
    assert body["reason"] == "ok"
    assert body["citations"][0]["doc_id"] == "ppt-002"
    assert body["request_id"]
    assert body["cached"] is False
    assert "question" not in body
    assert len(calls) == 1

    with sqlite3.connect(storage.database_path) as connection:
        row = connection.execute(
            "SELECT outcome, http_status, result_count FROM request_logs WHERE request_id = ?",
            (body["request_id"],),
        ).fetchone()

    assert row == ("answer", 200, 1)


def test_chat_caches_repeated_questions_but_logs_each_request(tmp_path, monkeypatch):
    client, storage, calls = make_client(tmp_path, monkeypatch)

    with client:
        first = client.post(
            "/chat",
            json={"question": "How much is the passport fee?"},
        )
        second = client.post(
            "/chat",
            json={"question": "  HOW MUCH is the passport fee?  "},
        )

    assert first.status_code == second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert len(calls) == 1

    with sqlite3.connect(storage.database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM request_logs").fetchone()[0]

    assert count == 2


def test_cached_answer_recomputes_privacy_notice(tmp_path, monkeypatch):
    client, _, calls = make_client(
        tmp_path,
        monkeypatch,
        answer_result(notices=["Original workflow notice"]),
    )

    with client:
        # First request contains a phone number that should be redacted.
        first = client.post(
            "/chat",
            json={"question": "What is the passport fee? My phone is 01712345678"},
        )

        # Second request has the same sanitized question, but no phone number.
        second = client.post(
            "/chat",
            json={"question": "What is the passport fee? My phone is [PHONE_NUMBER]"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["notices"]
    assert second.json()["notices"] == []
    assert len(calls) == 1


def test_chat_does_not_cache_unavailable_results(tmp_path, monkeypatch):
    result = answer_result(decision="unavailable", reason="llm_unavailable")
    client, storage, calls = make_client(tmp_path, monkeypatch, result)

    with client:
        first = client.post("/chat", json={"question": "Passport fee please"})
        second = client.post("/chat", json={"question": "Passport fee please"})

    assert first.status_code == second.status_code == 503
    assert first.json()["decision"] == "unavailable"
    assert second.json()["cached"] is False
    assert len(calls) == 2

    with sqlite3.connect(storage.database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM request_logs").fetchone()[0]

    assert count == 2


def test_chat_rate_limit_returns_429_and_retry_after(tmp_path, monkeypatch):
    client, _, _ = make_client(tmp_path, monkeypatch)

    with client:
        client.app.state.rate_limiter.limit = 1

        first = client.post("/chat", json={"question": "Passport fee please"})
        second = client.post("/chat", json={"question": "Passport fee please"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1


def test_chat_rejects_invalid_question_lengths(tmp_path, monkeypatch):
    client, _, _ = make_client(tmp_path, monkeypatch)

    with client:
        assert client.post("/chat", json={"question": "a"}).status_code == 422
        assert client.post("/chat", json={"question": "x" * 301}).status_code == 422
        assert client.post("/chat", json={}).status_code == 422


def test_feedback_accepts_rating_for_existing_request(tmp_path, monkeypatch):
    client, _, _ = make_client(tmp_path, monkeypatch)

    with client:
        chat = client.post("/chat", json={"question": "Passport fee please"})
        request_id = chat.json()["request_id"]
        response = client.post(
            "/feedback",
            json={
                "request_id": request_id,
                "rating": 1,
                "category": "accuracy",
            },
        )

    assert chat.status_code == 200
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["feedback_id"]


def test_feedback_rejects_unknown_request_id(tmp_path, monkeypatch):
    client, _, _ = make_client(tmp_path, monkeypatch)

    with client:
        response = client.post(
            "/feedback",
            json={"request_id": "unknown-request", "rating": -1},
        )

    assert response.status_code == 404


def test_feedback_rejects_invalid_rating_and_category(tmp_path, monkeypatch):
    client, _, _ = make_client(tmp_path, monkeypatch)

    with client:
        bad_rating = client.post(
            "/feedback",
            json={"request_id": "some-id", "rating": 0},
        )
        bad_category = client.post(
            "/feedback",
            json={
                "request_id": "some-id",
                "rating": -1,
                "category": "irrelevant",
            },
        )

    assert bad_rating.status_code == 422
    assert bad_category.status_code == 422
