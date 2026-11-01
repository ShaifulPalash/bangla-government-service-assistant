"""The web API for the Bangla Government-Service Assistant."""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.api.guards import AnswerCache, RateLimiter, visitor_id
from app.api.storage import SQLiteStorage
from app.config import get_settings
from app.graph.safety import message_for, safety_check
from app.graph.workflow import ask, build_graph
from app.indexing.embeddings import MODEL, EmbeddingError
from app.indexing.vector_index import IndexMismatchError
from app.llm.language import detect_language
from app.llm.providers import LLMError, build_chain
from app.logging_setup import setup_logging
from app.retrieval.hybrid import Retriever, build_retriever

logger = logging.getLogger(__name__)

SEARCH_MODE = "meaning"
EXCERPT_CHARS = 300

FeedbackCategory = Literal["accuracy", "incomplete", "outdated", "unclear", "other"]


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


class ChatRequest(BaseModel):
    """A question for the assistant."""

    question: str = Field(min_length=2, max_length=300)


class ChatResponse(BaseModel):
    """An answer and its provenance, without echoing the submitted question."""

    request_id: str
    decision: Literal["answer", "clarify", "refuse", "unavailable"]
    reason: str
    message: str
    language: str
    service: str | None = None
    citations: list[dict] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
    top_score: float | None = None
    provider: str | None = None
    model: str | None = None
    path: list[str] = Field(default_factory=list)
    took_ms: int
    cached: bool = False


class FeedbackRequest(BaseModel):
    """Structured feedback for a previously answered request."""

    request_id: str = Field(min_length=1, max_length=64)
    rating: Literal[1, -1]
    category: FeedbackCategory | None = None


class FeedbackResponse(BaseModel):
    feedback_id: str
    status: Literal["accepted"] = "accepted"


def default_retriever() -> Retriever:
    """Open the indexes and connect to the embedding service."""
    key = get_settings().gemini_api_key
    if key is None:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return build_retriever(key.get_secret_value())


def default_workflow(retriever: Retriever):
    """Build the production graph using the configured language-model providers."""
    return build_graph(retriever, build_chain(get_settings()))


def default_storage() -> SQLiteStorage:
    """Create the production SQLite storage instance."""
    return SQLiteStorage(get_settings().database_path)


def excerpt(text: str) -> str:
    """One-line preview of a passage."""
    flat = " ".join(text.split())
    return flat if len(flat) <= EXCERPT_CHARS else flat[:EXCERPT_CHARS].rstrip() + "..."


def create_app(
    retriever_factory: Callable[[], Retriever] = default_retriever,
    workflow_factory: Callable[[Retriever], object] | None = None,
    storage_factory: Callable[[], SQLiteStorage] | None = None,
) -> FastAPI:
    """Build an app with injectable dependencies for offline unit tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging(get_settings().log_level)
        logging.getLogger("httpx").setLevel(logging.WARNING)

        app.state.retriever = None
        app.state.startup_error = None
        app.state.graph = None
        app.state.workflow_error = None
        app.state.storage = None
        app.state.storage_error = None
        app.state.answer_cache = AnswerCache()
        app.state.rate_limiter = RateLimiter()

        if storage_factory is not None:
            try:
                app.state.storage = storage_factory()
                app.state.storage.initialize()
                logger.info("API storage ready")
            except (OSError, sqlite3.Error) as error:
                app.state.storage_error = type(error).__name__
                logger.error("API storage failed to initialize: %s", type(error).__name__)

        try:
            app.state.retriever = retriever_factory()
            logger.info("retriever ready")
        except (FileNotFoundError, IndexMismatchError, RuntimeError) as error:
            app.state.startup_error = str(error)
            logger.error("retriever failed to load: %s", error)

        if app.state.retriever is not None and workflow_factory is not None:
            try:
                app.state.graph = workflow_factory(app.state.retriever)
                logger.info("chat workflow ready")
            except (LLMError, RuntimeError, FileNotFoundError) as error:
                app.state.workflow_error = type(error).__name__
                logger.error("chat workflow failed to initialize: %s", type(error).__name__)

        yield

    app = FastAPI(
        title="Bangla Government-Service Assistant",
        version="0.4.0",
        lifespan=lifespan,
    )

    @app.get("/", include_in_schema=False)
    def root():
        """Send visitors to the interactive documentation."""
        return RedirectResponse(url="/docs")

    @app.get("/health", response_model=HealthResponse)
    def health():
        """Report search readiness, preserving the existing health contract."""
        retriever = app.state.retriever
        if retriever is None:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "detail": app.state.startup_error},
            )
        return HealthResponse(
            status="ok",
            chunks=retriever.collection.count(),
            embedding_model=MODEL,
        )

    @app.get("/search", response_model=SearchResponse)
    def search(
        q: str = Query(..., min_length=2, max_length=300),
        k: int = Query(3, ge=1, le=8),
        service: Literal["passport", "nid"] | None = None,
    ):
        """Find relevant passages without generating an answer."""
        retriever = app.state.retriever
        if retriever is None:
            return JSONResponse(
                status_code=503,
                content={"error": "search is not ready", "detail": app.state.startup_error},
            )

        started = time.perf_counter()
        try:
            results = retriever.retrieve(q, k=k, mode=SEARCH_MODE, service=service)
        except EmbeddingError:
            logger.error("embedding service unavailable during search")
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

    @app.post("/chat", response_model=ChatResponse)
    def chat(body: ChatRequest, request: Request):
        """Answer a question, with caching, rate limiting, and metadata-only logging."""
        started = time.perf_counter()

        cfg = get_settings()
        visitor = visitor_id(
            request.headers.get("x-forwarded-for"),
            request.client.host if request.client else None,
            cfg.trust_proxy_headers,
            cfg.proxy_hops,
        )
        allowed, retry_seconds = app.state.rate_limiter.allow(visitor)
        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_seconds)},
                content={"error": "too many requests; please try again shortly"},
            )

        storage = app.state.storage
        if storage is None:
            return JSONResponse(
                status_code=503,
                content={"error": "chat storage is unavailable"},
            )

        if app.state.graph is None:
            return JSONResponse(
                status_code=503,
                content={"error": "chat workflow is not ready"},
            )

        checked = safety_check(body.question)
        result = app.state.answer_cache.get(checked.question)
        cached = result is not None

        if result is None:
            try:
                result = ask(app.state.graph, body.question)
            except Exception as error:
                # Do not log exception text or the submitted question.
                logger.error("chat workflow execution failed: %s", type(error).__name__)
                return JSONResponse(
                    status_code=503,
                    content={"error": "the assistant is temporarily unavailable"},
                )
            app.state.answer_cache.put(checked.question, result)
        else:
            # A cached result must not carry a privacy notice from a different request.
            result = dict(result)
            result["notices"] = (
                [message_for("privacy", result.get("language", "en"))] if checked.redacted else []
            )

        took_ms = int((time.perf_counter() - started) * 1000)
        status_code = 503 if result["decision"] == "unavailable" else 200
        citations = result.get("citations") or []

        try:
            request_id = storage.log_request(
                service=result.get("service") or "unclear",
                outcome=result["decision"],
                http_status=status_code,
                latency_ms=took_ms,
                result_count=len(citations),
            )
        except (OSError, sqlite3.Error, ValueError) as error:
            logger.error("request metadata could not be saved: %s", type(error).__name__)
            return JSONResponse(
                status_code=503,
                content={"error": "request logging is temporarily unavailable"},
            )

        response = ChatResponse(
            request_id=request_id,
            decision=result["decision"],
            reason=result["reason"],
            message=result["message"],
            language=result.get("language", detect_language(checked.question)),
            service=result.get("service"),
            citations=citations,
            notices=result.get("notices") or [],
            top_score=result.get("top_score"),
            provider=result.get("provider"),
            model=result.get("model"),
            path=result.get("path") or [],
            took_ms=took_ms,
            cached=cached,
        )
        if status_code == 503:
            return JSONResponse(status_code=503, content=response.model_dump())
        return response

    @app.post("/feedback", response_model=FeedbackResponse)
    def feedback(body: FeedbackRequest):
        """Save a rating and optional category for an existing request."""
        storage = app.state.storage
        if storage is None:
            return JSONResponse(
                status_code=503,
                content={"error": "feedback storage is unavailable"},
            )

        try:
            feedback_id = storage.save_feedback(
                request_id=body.request_id,
                rating=body.rating,
                category=body.category,
            )
        except sqlite3.IntegrityError:
            # The request ID must refer to an existing logged request.
            return JSONResponse(
                status_code=404,
                content={"error": "request ID was not found"},
            )
        except (OSError, sqlite3.Error):
            logger.error("feedback could not be saved")
            return JSONResponse(
                status_code=503,
                content={"error": "feedback could not be saved; try again later"},
            )
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={"error": "invalid feedback"},
            )

        return FeedbackResponse(feedback_id=feedback_id)

    return app


# Production app: enable the workflow and persistent storage.
app = create_app(
    workflow_factory=default_workflow,
    storage_factory=default_storage,
)
