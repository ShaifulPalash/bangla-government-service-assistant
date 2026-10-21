"""Hybrid retrieval: search by meaning and by words, then fuse the two rankings.

Reciprocal Rank Fusion (RRF) gives every chunk 1 / (60 + position) from each list that
contains it, multiplied by a weight for that search method, and adds the results up.
A chunk that ranks well in both lists beats a chunk that ranks well in only one.
"""

from __future__ import annotations

import re
from pathlib import Path

import chromadb

from app.indexing.embeddings import Embedder
from app.indexing.keyword_index import KeywordIndex, load_keyword_index
from app.indexing.vector_index import open_collection, search_vectors

RRF_K = 60  # the usual constant: it keeps one very high rank from dominating
DEPTH = 20  # how many candidates each search contributes before fusion
MODES = ("meaning", "word", "hybrid")

DETAIL_FIELDS = (
    "chunk_id",
    "doc_id",
    "title",
    "url",
    "service",
    "language",
    "publisher",
    "page",
    "last_updated_date",
    "verified_date",
    "extraction",
    "text",
)
_CHUNK_ID = re.compile(r"^(?P<doc>.+)-p\d{3}-c\d+$")


def doc_id_of(chunk_id: str) -> str:
    """'nid-007-p003-c01' -> 'nid-007'."""
    match = _CHUNK_ID.match(chunk_id)
    return match.group("doc") if match else chunk_id


def reciprocal_rank_fusion(
    rankings: dict[str, list[str]],
    weights: dict[str, float] | None = None,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Fuse ranked lists of chunk ids. Returns (chunk_id, score), best first."""
    weights = weights or {}
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for method, chunk_ids in rankings.items():
        weight = weights.get(method, 1.0)
        for rank, chunk_id in enumerate(chunk_ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)
            best_rank[chunk_id] = min(best_rank.get(chunk_id, rank), rank)
    # Equal scores are ordered by best single rank, then by id, so results are repeatable.
    return sorted(scores.items(), key=lambda item: (-item[1], best_rank[item[0]], item[0]))


class Retriever:
    """Finds the chunks that best match a question."""

    def __init__(
        self,
        collection: chromadb.Collection,
        keyword_index: KeywordIndex,
        embedder: Embedder,
        depth: int = DEPTH,
    ) -> None:
        self.collection = collection
        self.keyword_index = keyword_index
        self.embedder = embedder
        self.depth = depth

    def _details(self, chunk_ids: list[str]) -> dict[str, dict]:
        """Text and metadata for chunks found by word search only."""
        if not chunk_ids:
            return {}
        result = self.collection.get(ids=chunk_ids, include=["documents", "metadatas"])
        details = {}
        for chunk_id, text, metadata in zip(
            result["ids"], result["documents"], result["metadatas"], strict=True
        ):
            record = {"chunk_id": chunk_id, "text": text}
            record.update({name: value for name, value in metadata.items() if name != "page"})
            record["page"] = metadata["page"] or None  # 0 means "no page"
            details[chunk_id] = record
        return details

    def retrieve(
        self,
        question: str,
        k: int = 8,
        mode: str = "hybrid",
        weights: dict[str, float] | None = None,
        service: str | None = None,
        exclude_docs: frozenset[str] = frozenset(),
    ) -> list[dict]:
        """Return up to k chunks, best first.

        mode:    "meaning", "word" or "hybrid".
        weights: how much each method counts in hybrid mode, e.g. {"meaning": 2, "word": 1}.
        service: "passport" or "nid" limits both searches to that service.
        score:   cosine similarity (meaning), BM25 (word) or the fused RRF score (hybrid).
        """
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        meaning_hits: list[dict] = []
        word_hits: list[dict] = []
        if mode in ("meaning", "hybrid"):
            vector = self.embedder.embed_query(question)
            found = search_vectors(self.collection, vector, k=self.depth, service=service)
            meaning_hits = [hit for hit in found if hit["doc_id"] not in exclude_docs]
        if mode in ("word", "hybrid"):
            found = self.keyword_index.search(question, k=self.depth, service=service)
            word_hits = [hit for hit in found if doc_id_of(hit["chunk_id"]) not in exclude_docs]

        meaning = {hit["chunk_id"]: (rank, hit) for rank, hit in enumerate(meaning_hits, start=1)}
        word = {hit["chunk_id"]: (rank, hit) for rank, hit in enumerate(word_hits, start=1)}
        if mode == "hybrid":
            rankings = {
                "meaning": [hit["chunk_id"] for hit in meaning_hits],
                "word": [hit["chunk_id"] for hit in word_hits],
            }
            ordered = reciprocal_rank_fusion(rankings, weights)
        elif mode == "meaning":
            ordered = [(hit["chunk_id"], hit["score"]) for hit in meaning_hits]
        else:
            ordered = [(hit["chunk_id"], hit["score"]) for hit in word_hits]
        ordered = ordered[:k]

        details = self._details([chunk_id for chunk_id, _ in ordered if chunk_id not in meaning])
        results = []
        for chunk_id, score in ordered:
            source = meaning[chunk_id][1] if chunk_id in meaning else details[chunk_id]
            record = {field: source[field] for field in DETAIL_FIELDS}
            record["score"] = score
            record["meaning_score"] = meaning[chunk_id][1]["score"] if chunk_id in meaning else None
            record["word_score"] = word[chunk_id][1]["score"] if chunk_id in word else None
            record["meaning_rank"] = meaning[chunk_id][0] if chunk_id in meaning else None
            record["word_rank"] = word[chunk_id][0] if chunk_id in word else None
            results.append(record)
        return results


def build_retriever(api_key: str, cache_path: Path | None = None) -> Retriever:
    """Open both indexes (checking model and tokenizer) and return a ready Retriever."""
    return Retriever(
        open_collection(), load_keyword_index(), Embedder(api_key, cache_path=cache_path)
    )
