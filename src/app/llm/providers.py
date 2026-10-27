"""Language-model clients with timeouts, limited retries, and a fallback chain.

A user is waiting, so we retry only twice with short waits. If a provider asks us to wait
longer than a few seconds, or keeps failing, the chain moves on to the next provider.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15.0
MAX_RETRIES = 2
MAX_RETRY_WAIT = 5.0  # seconds; a longer wait is not worth it, the next provider tries instead
RETRY_STATUSES = {429, 500, 502, 503, 504}

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    """Raised when a language model cannot give an answer."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int | None
    output_tokens: int | None
    latency_ms: int


def _error_message(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
        return (
            str(error.get("message", response.text[:200]))
            if isinstance(error, dict)
            else str(error)
        )
    except ValueError:
        return response.text[:200]


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after", "")
    return float(value) if value.replace(".", "", 1).isdigit() else None


def _is_daily_quota(status: int, message: str) -> bool:
    """True for a 429 that says the limit is per day: waiting a few seconds cannot help."""
    return status == 429 and "per day" in message.lower()


def post_json(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    body: dict,
    sleep: Callable[[float], None],
) -> dict:
    """POST and return the JSON reply. Retries only temporary problems, a couple of times."""
    problem = ""
    for attempt in range(MAX_RETRIES + 1):
        wait: float | None = None
        try:
            response = client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as error:
            # A timeout means the provider is slow right now. Do not wait again:
            # raise at once so the chain can hand over to the next provider.
            raise LLMError(f"timeout: {type(error).__name__}") from error
        except httpx.TransportError as error:
            problem = f"network error: {type(error).__name__}"
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as error:
                    raise LLMError("the provider sent a reply that is not JSON") from error
            problem = f"HTTP {response.status_code}: {_error_message(response)}"
            if response.status_code not in RETRY_STATUSES or _is_daily_quota(
                response.status_code, problem
            ):
                raise LLMError(problem)
            wait = _retry_after(response)
        if attempt == MAX_RETRIES:
            break
        wait = min(2.0**attempt, MAX_RETRY_WAIT) if wait is None else wait
        if wait > MAX_RETRY_WAIT:
            break
        logger.warning("llm call failed (%s), waiting %.0fs", problem, wait)
        sleep(wait)
    raise LLMError(f"gave up: {problem}")


class GeminiClient:
    provider = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
        self.sleep = sleep

    def generate(self, system: str, user: str, max_output_tokens: int = 800) -> LLMResult:
        # Gemini 3 models: keep thinking low (cheaper and faster) and leave temperature at
        # its default, as Google recommends for this model family.
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }
        started = time.perf_counter()
        data = post_json(
            self.client,
            GEMINI_URL.format(model=self.model),
            {"x-goog-api-key": self.api_key},
            body,
            self.sleep,
        )
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError(f"no answer (blocked?): {data.get('promptFeedback')}")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()
        if not text:
            raise LLMError(f"empty answer (finish reason: {candidates[0].get('finishReason')})")
        usage = data.get("usageMetadata", {})
        return LLMResult(
            text=text,
            provider=self.provider,
            model=self.model,
            prompt_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


class GroqClient:
    provider = "groq"

    def __init__(
        self,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        reasoning_effort: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
        self.sleep = sleep
        self.reasoning_effort = reasoning_effort

    def generate(self, system: str, user: str, max_output_tokens: int = 800) -> LLMResult:
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_completion_tokens": max_output_tokens,
        }
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        started = time.perf_counter()
        data = post_json(
            self.client, GROQ_URL, {"Authorization": f"Bearer {self.api_key}"}, body, self.sleep
        )
        choices = data.get("choices") or []
        text = (choices[0].get("message", {}).get("content") or "").strip() if choices else ""
        if not text:
            raise LLMError("empty answer")
        usage = data.get("usage", {})
        return LLMResult(
            text=text,
            provider=self.provider,
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


class FallbackChain:
    """Tries each client in order and returns the first answer."""

    def __init__(self, clients: list) -> None:
        self.clients = clients

    def generate(
        self,
        system: str,
        user: str,
        max_output_tokens: int = 800,
        accept: Callable[[str], bool] | None = None,
    ) -> LLMResult:
        """Return the first usable answer.

        `accept` can reject a reply (for example one that cannot be read). The next
        provider then gets a turn, exactly as when a provider is down.
        """
        problems = []
        for client in self.clients:
            try:
                result = client.generate(system, user, max_output_tokens=max_output_tokens)
            except LLMError as error:
                problems.append(f"{client.provider}/{client.model}: {error}")
                logger.warning("llm failed, trying the next one: %s", problems[-1])
                continue
            if accept is not None and not accept(result.text):
                problems.append(f"{client.provider}/{client.model}: unreadable reply")
                logger.warning(
                    "llm reply rejected (%d characters, starts: %r, ends: %r), trying the next one",
                    len(result.text),
                    result.text[:120],
                    result.text[-120:],
                )
                continue
            return result
        raise LLMError("all providers failed: " + " | ".join(problems))


def build_chain(settings: Settings) -> FallbackChain:
    """Groq first (fastest, no invented numbers in our bake-off), Gemini as the backup."""
    clients: list = []
    if settings.groq_api_key:
        clients.append(
            GroqClient(
                settings.groq_api_key.get_secret_value(),
                settings.groq_model,
                reasoning_effort="low",  # leaves more of the token budget for the answer
            )
        )
    if settings.gemini_api_key:
        clients.append(
            GeminiClient(settings.gemini_api_key.get_secret_value(), settings.gemini_model)
        )
    if not clients:
        raise LLMError("no language-model key is configured")
    return FallbackChain(clients)
