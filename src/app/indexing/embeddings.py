"""Turn text into embedding vectors with Google's gemini-embedding-2, politely and safely.

- One request per text inside a batch call (the model would otherwise merge all the
  texts of a request into ONE vector).
- A pause between calls, and retries with growing waits when the free tier says "slow down".
- A cache, so the same text is never embedded twice (and a crash loses nothing).
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CHUNKS_FILE = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"
CACHE_FILE = PROJECT_ROOT / "data" / "processed" / "embedding_cache.jsonl"

MODEL = "gemini-embedding-2"
DIMENSIONS = 768
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents"

BATCH_SIZE = 10  # texts per API call
PAUSE_SECONDS = 4.0  # wait between calls, to stay under free-tier limits
MAX_RETRIES = 5
RETRY_STATUSES = {429, 500, 502, 503, 504}  # temporary problems worth retrying


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be produced."""


def document_text(title: str | None, text: str) -> str:
    """Format a passage the way gemini-embedding-2 expects for documents."""
    return f"title: {title or 'none'} | text: {text}"


def query_text(question: str) -> str:
    """Format a question the way gemini-embedding-2 expects for search queries."""
    return f"task: search result | query: {question}"


def cache_key(text: str) -> str:
    """Cache key. It changes if the text, the model or the vector size changes."""
    raw = f"{MODEL}|{DIMENSIONS}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _error_message(response: httpx.Response) -> str:
    """The error text from Google, never including our key."""
    try:
        return str(response.json().get("error", {}).get("message", response.text[:200]))
    except ValueError:
        return response.text[:200]


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """How long the server asked us to wait, if it said."""
    value = response.headers.get("Retry-After", "")
    return float(value) if value.isdigit() else None


class Embedder:
    """Embeds texts with caching, batching, pauses and retries."""

    def __init__(
        self,
        api_key: str,
        cache_path: Path | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        pause: float = PAUSE_SECONDS,
    ) -> None:
        self.api_key = api_key
        self.cache_path = cache_path  # None means "keep the cache in memory only"
        self.client = client or httpx.Client(timeout=60)
        self.sleep = sleep
        self.pause = pause
        self.cache: dict[str, list[float]] = {}
        self.stats = {"from_cache": 0, "from_api": 0, "api_calls": 0}
        if cache_path is not None and cache_path.exists():
            self._load_cache(cache_path)

    def _load_cache(self, path: Path) -> None:
        with path.open(encoding="utf-8") as file:
            for line in file:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a half-written last line after a crash is simply skipped
                self.cache[row["key"]] = row["vector"]

    def _save(self, new: dict[str, list[float]]) -> None:
        if self.cache_path is None:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("a", encoding="utf-8") as file:
            for key, vector in new.items():
                file.write(json.dumps({"key": key, "vector": vector}) + "\n")

    def _request(self, texts: list[str]) -> list[list[float]]:
        """One batch call, retried with growing waits on temporary problems."""
        body = {
            "requests": [
                {
                    "model": f"models/{MODEL}",
                    "content": {"parts": [{"text": text}]},
                    "output_dimensionality": DIMENSIONS,
                }
                for text in texts
            ]
        }
        headers = {"x-goog-api-key": self.api_key}
        problem = ""
        for attempt in range(MAX_RETRIES + 1):
            retry_after = None
            try:
                response = self.client.post(URL, json=body, headers=headers)
            except httpx.TransportError as error:
                problem = f"network error: {error}"
            else:
                if response.status_code == 200:
                    return self._parse(response, len(texts))
                problem = f"HTTP {response.status_code}: {_error_message(response)}"
                if response.status_code not in RETRY_STATUSES:
                    raise EmbeddingError(problem)
                retry_after = _retry_after_seconds(response)
            if attempt == MAX_RETRIES:
                break
            wait = retry_after if retry_after is not None else min(5 * 2**attempt, 60)
            logger.warning("Embedding call failed (%s). Waiting %.0f seconds.", problem, wait)
            self.sleep(wait)
        raise EmbeddingError(f"gave up after {MAX_RETRIES + 1} attempts: {problem}")

    @staticmethod
    def _parse(response: httpx.Response, expected: int) -> list[list[float]]:
        vectors = [item["values"] for item in response.json().get("embeddings", [])]
        if len(vectors) != expected:
            raise EmbeddingError(f"expected {expected} vectors, got {len(vectors)}")
        if any(len(vector) != DIMENSIONS for vector in vectors):
            raise EmbeddingError(f"a vector did not have {DIMENSIONS} numbers")
        return vectors

    def embed(
        self, texts: list[str], progress: Callable[[int, int], None] | None = None
    ) -> list[list[float]]:
        """Embed texts (already formatted with their prefix). Only new texts reach the API."""
        keys = [cache_key(text) for text in texts]
        missing: dict[str, str] = {}
        for key, text in zip(keys, texts, strict=True):
            if key not in self.cache and key not in missing:
                missing[key] = text
        self.stats["from_cache"] += len(texts) - len(missing)
        self.stats["from_api"] += len(missing)

        items = list(missing.items())
        for start in range(0, len(items), BATCH_SIZE):
            batch = items[start : start + BATCH_SIZE]
            vectors = self._request([text for _, text in batch])
            new = {key: vector for (key, _), vector in zip(batch, vectors, strict=True)}
            self.cache.update(new)
            self._save(new)
            self.stats["api_calls"] += 1
            if progress:
                progress(min(start + BATCH_SIZE, len(items)), len(items))
            if start + BATCH_SIZE < len(items):
                self.sleep(self.pause)
        return [self.cache[key] for key in keys]

    def embed_documents(
        self, chunks: list[dict], progress: Callable[[int, int], None] | None = None
    ) -> list[list[float]]:
        """Embed chunk records (uses their title and text)."""
        texts = [document_text(chunk.get("title"), chunk["text"]) for chunk in chunks]
        return self.embed(texts, progress)

    def embed_query(self, question: str) -> list[float]:
        """Embed one user question."""
        return self.embed([query_text(question)])[0]


def main() -> int:
    """Embed every chunk in chunks.jsonl and store the vectors in the cache file."""
    key = get_settings().gemini_api_key
    if key is None:
        print("GEMINI_API_KEY is empty in .env")
        return 1
    if not CHUNKS_FILE.exists():
        print("chunks.jsonl not found. Run: make build-chunks")
        return 1
    with CHUNKS_FILE.open(encoding="utf-8") as file:
        chunks = [json.loads(line) for line in file]
    embedder = Embedder(key.get_secret_value(), cache_path=CACHE_FILE)
    started = time.time()

    def show(done: int, total: int) -> None:
        print(f"  embedded {done}/{total} new chunks ({time.time() - started:.0f}s)")

    try:
        embedder.embed_documents(chunks, progress=show)
    except EmbeddingError as error:
        print(f"FAILED: {error}")
        print("Progress is saved. Run the command again to continue.")
        return 1
    stats = embedder.stats
    print(
        f"\n{len(chunks)} chunks ready | from cache: {stats['from_cache']} | "
        f"from API: {stats['from_api']} | API calls: {stats['api_calls']}"
    )
    size_mb = CACHE_FILE.stat().st_size / 1_000_000
    print(f"cache: {CACHE_FILE.relative_to(PROJECT_ROOT).as_posix()} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
