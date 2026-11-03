"""Tests that the per-visitor rate limit comes from a setting."""

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.storage import SQLiteStorage
from app.config import Settings


def make_app(tmp_path, monkeypatch, **settings):
    monkeypatch.setattr("app.api.main.get_settings", lambda: Settings(_env_file=None, **settings))
    return create_app(
        retriever_factory=lambda: object(),
        workflow_factory=lambda retriever: object(),
        storage_factory=lambda: SQLiteStorage(tmp_path / "api.sqlite3"),
    )


def test_the_default_limit_is_ten_per_minute(tmp_path, monkeypatch):
    with TestClient(make_app(tmp_path, monkeypatch)) as client:
        assert client.app.state.rate_limiter.limit == 10


def test_the_limit_follows_the_setting(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch, rate_limit_per_minute=30)
    with TestClient(app) as client:
        assert client.app.state.rate_limiter.limit == 30
