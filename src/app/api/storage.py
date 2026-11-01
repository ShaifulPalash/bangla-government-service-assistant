"""Privacy-conscious SQLite storage for API request logs and feedback."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

FEEDBACK_CATEGORIES = (
    "accuracy",
    "incomplete",
    "outdated",
    "unclear",
    "other",
)


class SQLiteStorage:
    """Persist request metadata and structured feedback, never question text."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = ":memory:" if str(database_path) == ":memory:" else Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        """Open a connection and return rows by column name."""
        if self.database_path != ":memory:":
            self.database_path.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create the database tables if they do not already exist."""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS request_logs (
                    request_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    service TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    http_status INTEGER NOT NULL,
                    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
                    result_count INTEGER NOT NULL CHECK (result_count >= 0)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    rating INTEGER NOT NULL CHECK (rating IN (1, -1)),
                    category TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (request_id)
                        REFERENCES request_logs (request_id),
                    CHECK (
                        category IS NULL OR
                        category IN (
                            'accuracy', 'incomplete', 'outdated',
                            'unclear', 'other'
                        )
                    )
                )
                """
            )

    def log_request(
        self,
        *,
        service: str,
        outcome: str,
        http_status: int,
        latency_ms: int,
        result_count: int,
    ) -> str:
        """Save request metadata and return its generated ID."""
        if latency_ms < 0 or result_count < 0:
            raise ValueError("latency_ms and result_count must be non-negative")
        if not 100 <= http_status <= 599:
            raise ValueError("http_status must be between 100 and 599")
        if not service.strip() or not outcome.strip():
            raise ValueError("service and outcome must not be empty")

        request_id = str(uuid4())
        timestamp = datetime.now(UTC).isoformat()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO request_logs (
                    request_id, timestamp, service, outcome,
                    http_status, latency_ms, result_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    timestamp,
                    service,
                    outcome,
                    http_status,
                    latency_ms,
                    result_count,
                ),
            )

        return request_id

    def save_feedback(
        self,
        *,
        request_id: str,
        rating: int,
        category: str | None = None,
    ) -> str:
        """Save structured feedback for an existing request."""
        if rating not in (-1, 1):
            raise ValueError("rating must be 1 or -1")
        if category is not None and category not in FEEDBACK_CATEGORIES:
            raise ValueError("unsupported feedback category")

        feedback_id = str(uuid4())
        timestamp = datetime.now(UTC).isoformat()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback (
                    feedback_id, request_id, rating, category, timestamp
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (feedback_id, request_id, rating, category, timestamp),
            )

        return feedback_id
