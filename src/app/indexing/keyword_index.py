"""Build and query the BM25 keyword index (search by words).

BM25 scores each chunk by how many of the question's words it contains, giving more
weight to rare words. It finds exact things, such as a form number or a fee amount,
that search-by-meaning can miss. Chunks and questions use the same tokenizer.

Usage:
    python -m app.indexing.keyword_index                 build the index
    python -m app.indexing.keyword_index "question"      try a search
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.indexing.embeddings import CHUNKS_FILE
from app.indexing.tokenizer import tokenize
from app.indexing.vector_index import IndexMismatchError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INDEX_FILE = PROJECT_ROOT / "data" / "index" / "bm25.json"

# The index stores how the tokenizer cut this sentence. If the tokenizer changes later,
# the stored result no longer matches and the index refuses to load.
TOKENIZER_PROBE = "ই-পাসপোর্ট ফি ১২০০ টাকা। Passport Fee 1200!"


class KeywordIndex:
    """A loaded BM25 index."""

    def __init__(self, chunk_ids: list[str], services: list[str], tokens: list[list[str]]) -> None:
        self.chunk_ids = chunk_ids
        self.services = services
        self.tokens = tokens
        self.bm25 = BM25Okapi(tokens)

    def search(self, query: str, k: int = 8, service: str | None = None) -> list[dict]:
        """Return up to k chunks that share at least one word with the query, best first."""
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = self.bm25.get_scores(query_tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits: list[dict] = []
        for i in ranked:
            if scores[i] <= 0:
                break  # the rest share no word with the query
            if service and self.services[i] != service:
                continue
            hits.append({"chunk_id": self.chunk_ids[i], "score": float(scores[i])})
            if len(hits) == k:
                break
        return hits


def chunk_tokens(chunk: dict) -> list[str]:
    """The words of a chunk: its document title plus its text."""
    return tokenize(f"{chunk.get('title') or ''} {chunk['text']}")


def build_keyword_index(chunks: list[dict], index_file: Path = INDEX_FILE) -> KeywordIndex:
    """Tokenize every chunk, save the result, and return the ready index."""
    if not chunks:
        raise ValueError("no chunks to index")
    data = {
        "tokenizer_check": tokenize(TOKENIZER_PROBE),
        "chunk_ids": [chunk["chunk_id"] for chunk in chunks],
        "services": [chunk["service"] for chunk in chunks],
        "tokens": [chunk_tokens(chunk) for chunk in chunks],
    }
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return KeywordIndex(data["chunk_ids"], data["services"], data["tokens"])


def load_keyword_index(index_file: Path = INDEX_FILE) -> KeywordIndex:
    """Load the saved index, but only if the tokenizer still behaves the same."""
    if not index_file.exists():
        raise FileNotFoundError("Keyword index not found. Run: make build-keyword-index")
    data = json.loads(index_file.read_text(encoding="utf-8"))
    if data.get("tokenizer_check") != tokenize(TOKENIZER_PROBE):
        raise IndexMismatchError("The tokenizer changed since the index was built. Rebuild it.")
    return KeywordIndex(data["chunk_ids"], data["services"], data["tokens"])


def read_chunks() -> list[dict]:
    with CHUNKS_FILE.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file]


def build_command() -> int:
    if not CHUNKS_FILE.exists():
        print("chunks.jsonl not found. Run: make build-chunks")
        return 1
    chunks = read_chunks()
    index = build_keyword_index(chunks)
    vocabulary = {token for tokens in index.tokens for token in tokens}
    average = sum(len(tokens) for tokens in index.tokens) / len(index.tokens)
    print(f"built keyword index: {len(chunks)} chunks | {len(vocabulary)} different words")
    print(f"average chunk length: {average:.0f} words")

    # Self-check: the 8 rarest words of a chunk must bring that chunk back among the top 3
    # results. A result with exactly the same words also counts, because two identical
    # chunks cannot be told apart by any search.
    loaded = load_keyword_index()
    position = {chunk_id: i for i, chunk_id in enumerate(loaded.chunk_ids)}
    chunks_with_word = Counter(word for tokens in loaded.tokens for word in set(tokens))
    step = max(1, len(chunks) // 5)
    sample = chunks[::step][:5]
    found = 0
    for chunk in sample:
        own_words = loaded.tokens[position[chunk["chunk_id"]]]
        rarest = sorted(set(own_words), key=lambda word: (chunks_with_word[word], word))[:8]
        found += any(
            hit["chunk_id"] == chunk["chunk_id"]
            or loaded.tokens[position[hit["chunk_id"]]] == own_words
            for hit in loaded.search(" ".join(rarest), k=3)
        )
    print(f"self-check: {found}/{len(sample)} sample chunks found in their own top 3")
    print(f"index file: {INDEX_FILE.relative_to(PROJECT_ROOT).as_posix()}")
    return 0 if found == len(sample) else 1


def search_command(query: str) -> int:
    index = load_keyword_index()
    by_id = {chunk["chunk_id"]: chunk for chunk in read_chunks()}
    hits = index.search(query, k=5)
    if not hits:
        print("no chunk shares a word with that question")
    for rank, hit in enumerate(hits, start=1):
        chunk = by_id[hit["chunk_id"]]
        snippet = chunk["text"][:90].replace("\n", " ")
        print(f"{rank}. {hit['chunk_id']}  score {hit['score']:.2f}  [{chunk['service']}]")
        print(f"   {chunk['title']}: {snippet}")
    return 0


def main(argv: list[str]) -> int:
    return search_command(" ".join(argv)) if argv else build_command()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
