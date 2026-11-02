"""Talks to the assistant's web API for the Streamlit page.

There is no Streamlit code here, so it can be tested without a browser or a network.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

DEFAULT_API_URL = "https://bangla-gov-api.onrender.com"
FEEDBACK_CATEGORIES = ("accuracy", "incomplete", "outdated", "unclear", "other")


class ApiError(RuntimeError):
    """A problem the page can explain to the visitor. `kind` says what happened:
    "busy" (too many requests), "timeout", "unavailable" or "invalid" (bad question).
    """

    def __init__(self, kind: str, retry_after: int | None = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.retry_after = retry_after


@dataclass(frozen=True)
class Answer:
    """What the API said, with safe defaults for every field."""

    request_id: str
    decision: str  # "answer", "clarify", "refuse" or "unavailable"
    reason: str
    message: str
    language: str
    citations: list[dict] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    path: list[str] = field(default_factory=list)
    took_ms: int = 0
    cached: bool = False


def _to_answer(data: dict) -> Answer:
    return Answer(
        request_id=str(data.get("request_id", "")),
        decision=str(data.get("decision", "unavailable")),
        reason=str(data.get("reason", "")),
        message=str(data.get("message", "")),
        language=str(data.get("language", "en")),
        citations=list(data.get("citations") or []),
        notices=list(data.get("notices") or []),
        provider=data.get("provider"),
        model=data.get("model"),
        path=list(data.get("path") or []),
        took_ms=int(data.get("took_ms") or 0),
        cached=bool(data.get("cached")),
    )


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("retry-after", "")
    return int(value) if value.isdigit() else None


class ApiClient:
    def __init__(
        self,
        base_url: str = DEFAULT_API_URL,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client or httpx.Client(base_url=base_url, timeout=timeout)
        self.sleep = sleep

    def wake_up(self, attempts: int = 6, pause: float = 10.0) -> bool:
        """Ping /health until the server answers. A free host can need about a minute."""
        for attempt in range(attempts):
            try:
                if self.client.get("/health", timeout=15.0).status_code == 200:
                    return True
            except httpx.HTTPError:
                pass  # still asleep: wait and try again
            if attempt < attempts - 1:
                self.sleep(pause)
        return False

    def ask(self, question: str) -> Answer:
        """Send a question. Raises ApiError for problems the page should explain."""
        try:
            response = self.client.post("/chat", json={"question": question})
        except httpx.TimeoutException as error:
            raise ApiError("timeout") from error
        except httpx.TransportError as error:
            raise ApiError("unavailable") from error
        if response.status_code == 429:
            raise ApiError("busy", _retry_after(response))
        if response.status_code == 422:
            raise ApiError("invalid")
        try:
            data = response.json()
        except ValueError as error:
            raise ApiError("unavailable") from error
        # The API answers 503 with a normal body when the language models are down.
        if response.status_code in (200, 503) and isinstance(data, dict) and "decision" in data:
            return _to_answer(data)
        raise ApiError("unavailable")

    def send_feedback(self, request_id: str, rating: int, category: str | None = None) -> bool:
        """Best effort: a failed feedback call must never disturb the visitor."""
        payload: dict = {"request_id": request_id, "rating": rating}
        if category in FEEDBACK_CATEGORIES:
            payload["category"] = category
        try:
            return self.client.post("/feedback", json=payload).status_code == 200
        except httpx.HTTPError:
            return False
