import sqlite3

import pytest

from app.api.storage import FEEDBACK_CATEGORIES, SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    """Use a fresh database for each test."""
    instance = SQLiteStorage(tmp_path / "test.sqlite3")
    instance.initialize()
    return instance


def log_request(storage, **overrides):
    values = {
        "service": "passport",
        "outcome": "success",
        "http_status": 200,
        "latency_ms": 125,
        "result_count": 3,
    }
    values.update(overrides)
    return storage.log_request(**values)


def test_initialize_creates_both_tables(storage):
    with sqlite3.connect(storage.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert {"request_logs", "feedback"} <= tables


def test_log_request_returns_id_and_persists_metadata(storage):
    request_id = log_request(storage)

    with sqlite3.connect(storage.database_path) as connection:
        row = connection.execute(
            """
            SELECT request_id, timestamp, service, outcome,
                   http_status, latency_ms, result_count
            FROM request_logs WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == request_id
    assert row[1]  # timestamp exists
    assert row[2:] == ("passport", "success", 200, 125, 3)


def test_log_request_does_not_store_question_text(storage):
    log_request(storage)

    with sqlite3.connect(storage.database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(request_logs)")}

    assert "question" not in columns
    assert "query" not in columns
    assert "request_body" not in columns


@pytest.mark.parametrize(
    "overrides",
    [
        {"latency_ms": -1},
        {"result_count": -1},
        {"http_status": 99},
        {"http_status": 600},
        {"service": ""},
        {"outcome": ""},
    ],
)
def test_log_request_rejects_invalid_metadata(storage, overrides):
    with pytest.raises(ValueError):
        log_request(storage, **overrides)


def test_save_feedback_persists_rating_and_category(storage):
    request_id = log_request(storage)

    feedback_id = storage.save_feedback(
        request_id=request_id,
        rating=1,
        category="accuracy",
    )

    with sqlite3.connect(storage.database_path) as connection:
        row = connection.execute(
            """
            SELECT feedback_id, request_id, rating, category, timestamp
            FROM feedback WHERE feedback_id = ?
            """,
            (feedback_id,),
        ).fetchone()

    assert row is not None
    assert row[:4] == (feedback_id, request_id, 1, "accuracy")
    assert row[4]


@pytest.mark.parametrize("rating", [0, 2, -2])
def test_save_feedback_rejects_invalid_rating(storage, rating):
    request_id = log_request(storage)

    with pytest.raises(ValueError, match="rating"):
        storage.save_feedback(request_id=request_id, rating=rating)


def test_save_feedback_rejects_unknown_category(storage):
    request_id = log_request(storage)

    with pytest.raises(ValueError, match="category"):
        storage.save_feedback(
            request_id=request_id,
            rating=1,
            category="personal-comment",
        )


def test_save_feedback_rejects_unknown_request_id(storage):
    with pytest.raises(sqlite3.IntegrityError):
        storage.save_feedback(
            request_id="nonexistent-request",
            rating=1,
        )


def test_feedback_categories_are_predefined():
    assert FEEDBACK_CATEGORIES == (
        "accuracy",
        "incomplete",
        "outdated",
        "unclear",
        "other",
    )
