"""The web API.

spike: /health and /search.

Run locally:  PYTHONPATH=src uvicorn app.api.main:app --port 8000
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.indexing.embeddings import MODEL, EmbeddingError
from app.indexing.vector_index import IndexMismatchError
from app.logging_setup import setup_logging
from app.retrieval.hybrid import Retriever, build_retriever

logger = logging.getLogger(__name__)

SEARCH_MODE = "meaning"  # measured best on the dev set (eval/results/variants-dev.json)
EXCERPT_CHARS = 300


class SearchHit(BaseModel):
    """One passage that matches the question."""

    chunk_id: str
    doc_id: str
    title: str
    url: str
    service: str
    page: int | None
    score: float
    last_updated_date: str | None
    verified_date: str
    excerpt: str


class SearchResponse(BaseModel):
    question: str
    hits: list[SearchHit]
    took_ms: int


class HealthResponse(BaseModel):
    status: str
    chunks: int
    embedding_model: str


def default_retriever() -> Retriever:
    """Open the indexes and connect to the embedding service (needs GEMINI_API_KEY)."""
    key = get_settings().gemini_api_key
    if key is None:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return build_retriever(key.get_secret_value())


def excerpt(text: str) -> str:
    """One-line preview of a passage."""
    flat = " ".join(text.split())
    return flat if len(flat) <= EXCERPT_CHARS else flat[:EXCERPT_CHARS].rstrip() + "..."


def create_app(retriever_factory: Callable[[], Retriever] = default_retriever) -> FastAPI:
    """Build the app. Tests pass their own factory, so they need no index and no network."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging(get_settings().log_level)
        logging.getLogger("httpx").setLevel(logging.WARNING)  # do not log every request line
        app.state.retriever = None
        app.state.startup_error = None
        try:
            app.state.retriever = retriever_factory()
            logger.info("retriever ready")
        except (FileNotFoundError, IndexMismatchError, RuntimeError) as error:
            app.state.startup_error = str(error)
            logger.error("retriever failed to load: %s", error)
        yield

    app = FastAPI(title="Bangla Government-Service Assistant", version="0.3.0", lifespan=lifespan)

    @app.get("/health", response_model=HealthResponse)
    def health():
        """Is the service ready? Render calls this to decide if the app is alive."""
        retriever = app.state.retriever
        if retriever is None:
            return JSONResponse(
                status_code=503, content={"status": "degraded", "detail": app.state.startup_error}
            )
        return HealthResponse(
            status="ok", chunks=retriever.collection.count(), embedding_model=MODEL
        )

    @app.get("/search", response_model=SearchResponse)
    def search(
        q: str = Query(..., min_length=2, max_length=300),
        k: int = Query(3, ge=1, le=8),
        service: Literal["passport", "nid"] | None = None,
    ):
        """Find the passages that best match a question (no answer is generated here)."""
        retriever = app.state.retriever
        if retriever is None:
            return JSONResponse(
                status_code=503,
                content={"error": "search is not ready", "detail": app.state.startup_error},
            )
        started = time.perf_counter()
        try:
            results = retriever.retrieve(q, k=k, mode=SEARCH_MODE, service=service)
        except EmbeddingError as error:
            logger.error("embedding failed: %s", error)
            return JSONResponse(
                status_code=502,
                content={"error": "the embedding service is unavailable, try again shortly"},
            )
        took_ms = int((time.perf_counter() - started) * 1000)
        hits = [
            SearchHit(
                chunk_id=result["chunk_id"],
                doc_id=result["doc_id"],
                title=result["title"],
                url=result["url"],
                service=result["service"],
                page=result["page"],
                score=result["score"],
                last_updated_date=result["last_updated_date"] or None,
                verified_date=result["verified_date"],
                excerpt=excerpt(result["text"]),
            )
            for result in results
        ]
        top = hits[0].score if hits else 0.0
        logger.info(
            "search q_len=%d k=%d service=%s hits=%d top=%.2f took_ms=%d",
            len(q),
            k,
            service,
            len(hits),
            top,
            took_ms,
        )
        return SearchResponse(question=q, hits=hits, took_ms=took_ms)

    return app


app = create_app()
