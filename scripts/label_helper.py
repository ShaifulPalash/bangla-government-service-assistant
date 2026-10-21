"""Labelling Helper

For each question it prints the draft expected documents and the top passages
from both searches, so a human can confirm the labels against the real text.
It changes nothing: you edit eval/dataset.jsonl yourself.

Usage:
  python scripts/label_helper.py q001 q002      # show these questions
  python scripts/label_helper.py                # show every answerable question
  python scripts/label_helper.py --chunk ppt-002-p000-c02   # full text of one passage
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from app.config import get_settings
from app.indexing.embeddings import PROJECT_ROOT, Embedder
from app.indexing.keyword_index import load_keyword_index, read_chunks
from app.indexing.vector_index import open_collection, search_vectors

DATASET = PROJECT_ROOT / "eval" / "dataset.jsonl"
# Question vectors share the cache file used by scripts/compare_search.py.
QUERY_CACHE = PROJECT_ROOT / "data" / "processed" / "query_cache.jsonl"
TOP_K = 4
EXCERPT_CHARS = 220


def read_questions() -> list[dict]:
    """Read the dataset file: one JSON object per line."""
    questions = []
    with DATASET.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                questions.append(json.loads(line))
    return questions


def excerpt(text: str, limit: int = EXCERPT_CHARS) -> str:
    """Start of a passage on a single line, so the terminal output stays short."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + " ..."


def show_hits(title: str, hits: list[dict], expected: set[str], by_id: dict) -> None:
    """Print one search's results and mark passages from the draft expected documents."""
    print(f"\n  {title}")
    if not hits:
        print("  (no results)")
    for rank, hit in enumerate(hits, start=1):
        chunk = by_id[hit["chunk_id"]]
        mark = "   <-- expected doc" if chunk["doc_id"] in expected else ""
        print(f"  {rank}. {hit['score']:.3f}  {hit['chunk_id']}{mark}")
        print(f"       {excerpt(chunk['text'])}")


def show_chunk(chunk_id: str, by_id: dict) -> int:
    """Print the full text of one passage."""
    chunk = by_id.get(chunk_id)
    if chunk is None:
        print(f"No passage with id {chunk_id}")
        return 1
    print(f"{chunk_id} | {chunk['title']} | page {chunk['page']}")
    print(f"url: {chunk['url']}")
    print("-" * 80)
    print(chunk["text"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Show search results for labelling.")
    parser.add_argument("ids", nargs="*", help="question ids, e.g. q001 q002")
    parser.add_argument("--chunk", help="print the full text of this passage id")
    args = parser.parse_args()

    by_id = {chunk["chunk_id"]: chunk for chunk in read_chunks()}
    if args.chunk:
        return show_chunk(args.chunk, by_id)

    questions = read_questions()
    if args.ids:
        wanted = set(args.ids)
        questions = [q for q in questions if q.get("id") in wanted]
        missing = wanted - {q.get("id") for q in questions}
        if missing:
            print(f"Unknown question ids: {sorted(missing)}")
            return 1
    else:
        questions = [q for q in questions if q.get("type") == "answerable"]

    key = get_settings().gemini_api_key
    if key is None:
        print("GEMINI_API_KEY is empty in .env")
        return 1
    embedder = Embedder(key.get_secret_value(), cache_path=QUERY_CACHE)
    collection = open_collection()
    keyword = load_keyword_index()

    for q in questions:
        expected = set(q.get("expected_docs", []))
        print("=" * 80)
        print(f"{q.get('id')}  [{q.get('language')}]  {q.get('type')}  split={q.get('split')}")
        print(f"QUESTION: {q.get('question')}")
        print(f"EXPECTED DOCS (draft): {sorted(expected)}")
        print(f"EVIDENCE NOW: {q.get('evidence', [])}")

        calls_before = embedder.stats["api_calls"]
        vector = embedder.embed_query(q["question"])
        meaning = search_vectors(collection, vector, k=TOP_K)
        show_hits("MEANING SEARCH", meaning, expected, by_id)
        show_hits("WORD SEARCH", keyword.search(q["question"], k=TOP_K), expected, by_id)

        if embedder.stats["api_calls"] > calls_before:
            time.sleep(4)  # be gentle with the free tier
    return 0


if __name__ == "__main__":
    sys.exit(main())
