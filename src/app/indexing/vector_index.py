"""Build and query the Chroma vector index (search by meaning).

The index is built from chunks.jsonl plus the cached embedding vectors, so building it
makes no API calls. It records the embedding model name and vector size, and refuses to
open if they do not match the code (vectors from different models cannot be compared).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError

from app.indexing.embeddings import (
    CACHE_FILE,
    CHUNKS_FILE,
    DIMENSIONS,
    MODEL,
    Embedder,
    cache_key,
    document_text,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INDEX_DIR = PROJECT_ROOT / "data" / "index" / "chroma"
COLLECTION_NAME = "chunks"
PREFIX_STYLE = "gemini-embedding-2: 'title | text' for documents, 'task | query' for questions"

# Chunk fields stored next to each vector. Chroma cannot store None, so None becomes "".
METADATA_FIELDS = (
    "doc_id",
    "title",
    "url",
    "service",
    "language",
    "publisher",
    "last_updated_date",
    "verified_date",
    "extraction",
)


class IndexMismatchError(RuntimeError):
    """Raised when the index was built with a different model or vector size."""


def _client(index_dir: Path) -> chromadb.ClientAPI:
    return chromadb.PersistentClient(
        path=str(index_dir), settings=Settings(anonymized_telemetry=False)
    )


def _metadata(chunk: dict) -> dict:
    metadata = {field: chunk.get(field) or "" for field in METADATA_FIELDS}
    metadata["page"] = chunk["page"] if chunk.get("page") is not None else 0  # 0 = no page
    return metadata


def build_index(
    chunks: list[dict],
    vectors: list[list[float]],
    index_dir: Path = INDEX_DIR,
    model: str = MODEL,
    dimensions: int = DIMENSIONS,
) -> chromadb.Collection:
    """Create (or replace) the vector index from chunks and their ready-made vectors."""
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors must have the same length")
    if any(len(vector) != dimensions for vector in vectors):
        raise ValueError(f"every vector must have {dimensions} numbers")
    index_dir.mkdir(parents=True, exist_ok=True)
    client = _client(index_dir)
    try:
        client.delete_collection(COLLECTION_NAME)
    except NotFoundError:
        pass  # first build: nothing to replace
    collection = client.create_collection(
        name=COLLECTION_NAME,
        configuration={"hnsw": {"space": "cosine"}},
        metadata={
            "embedding_model": model,
            "dimensions": dimensions,
            "prefix_style": PREFIX_STYLE,
            "chunk_count": len(chunks),
        },
        embedding_function=None,  # we always supply our own vectors
    )
    for start in range(0, len(chunks), 100):
        part = slice(start, start + 100)
        collection.add(
            ids=[chunk["chunk_id"] for chunk in chunks[part]],
            embeddings=vectors[part],
            documents=[chunk["text"] for chunk in chunks[part]],
            metadatas=[_metadata(chunk) for chunk in chunks[part]],
        )
    return collection


def open_collection(
    index_dir: Path = INDEX_DIR, model: str = MODEL, dimensions: int = DIMENSIONS
) -> chromadb.Collection:
    """Open the index, but only if it was built with the model and size the code uses."""
    if not index_dir.exists():
        raise FileNotFoundError("Vector index not found. Run: make build-vector-index")
    try:
        collection = _client(index_dir).get_collection(COLLECTION_NAME, embedding_function=None)
    except NotFoundError as error:
        raise FileNotFoundError("Vector index is empty. Run: make build-vector-index") from error
    built = collection.metadata or {}
    if built.get("embedding_model") != model or built.get("dimensions") != dimensions:
        raise IndexMismatchError(
            f"Index was built with {built.get('embedding_model')} "
            f"({built.get('dimensions')} dims) but the code uses {model} "
            f"({dimensions} dims). Rebuild the index."
        )
    return collection


def search_vectors(
    collection: chromadb.Collection,
    query_vector: list[float],
    k: int = 8,
    service: str | None = None,
) -> list[dict]:
    """Return the k nearest chunks. score is cosine similarity (1.0 = same direction)."""
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=k,
        where={"service": service} if service else None,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    rows = zip(
        result["ids"][0],
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
        strict=True,
    )
    for chunk_id, text, metadata, distance in rows:
        hit = {"chunk_id": chunk_id, "score": 1.0 - distance, "text": text}
        hit.update({name: value for name, value in metadata.items() if name != "page"})
        hit["page"] = metadata["page"] or None  # 0 means "no page"
        hits.append(hit)
    return hits


def main() -> int:
    """Build the index from chunks.jsonl and cached vectors, then check it."""
    if not CHUNKS_FILE.exists():
        print("chunks.jsonl not found. Run: make build-chunks")
        return 1
    with CHUNKS_FILE.open(encoding="utf-8") as file:
        chunks = [json.loads(line) for line in file]
    cache = Embedder(api_key="", cache_path=CACHE_FILE).cache  # reads the cache file only
    vectors = []
    missing = 0
    for chunk in chunks:
        vector = cache.get(cache_key(document_text(chunk.get("title"), chunk["text"])))
        if vector is None:
            missing += 1
        else:
            vectors.append(vector)
    if missing:
        print(f"{missing} chunks have no cached vector. Run: make embed-chunks")
        return 1

    collection = build_index(chunks, vectors)
    print(f"built index: {collection.count()} chunks | {MODEL} | {DIMENSIONS} dimensions")

    # Self-check with no API call: a few chunks, searched with their own vectors,
    # must come back as their own top result (same text, score near 1).
    reopened = open_collection()
    step = max(1, len(chunks) // 5)
    sample = list(zip(chunks[::step], vectors[::step], strict=True))[:5]
    found = 0
    for chunk, vector in sample:
        top = search_vectors(reopened, vector, k=1)[0]
        found += top["score"] > 0.99 and top["text"] == chunk["text"]
    print(f"self-check: {found}/{len(sample)} sample chunks found themselves as the top result")
    size = sum(path.stat().st_size for path in INDEX_DIR.rglob("*") if path.is_file())
    print(f"index folder: {INDEX_DIR.relative_to(PROJECT_ROOT).as_posix()} ({size / 1e6:.1f} MB)")
    return 0 if found == len(sample) else 1


if __name__ == "__main__":
    sys.exit(main())
