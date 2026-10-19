"""Try the two search indexes side by side on a few real questions.

For each question we print:
  - the top results of the meaning search (Chroma + Gemini embeddings)
  - the top results of the word search (BM25)
At the end we print the peak memory used. Nothing here changes the indexes.
"""

from __future__ import annotations

import resource
import sys
import time

from app.config import get_settings
from app.indexing.embeddings import PROJECT_ROOT, Embedder
from app.indexing.keyword_index import load_keyword_index, read_chunks
from app.indexing.vector_index import open_collection, search_vectors

# Question vectors get their own cache file, so they never mix with document vectors.
QUERY_CACHE = PROJECT_ROOT / "data" / "processed" / "query_cache.jsonl"

TOP_K = 5

QUESTIONS = [
    "পাসপোর্ট ফি কত?",  # Bangla question, the answer is on an English page
    "How much does an e-passport cost?",  # same question in English
    "My NID card is lost, what should I do?",  # English NID question
    "এনআইডি কার্ডে নাম সংশোধন করতে কী লাগবে?",  # Bangla NID correction question
    "What is the weather in Dhaka today?",  # out of scope: we should see weak scores
]


def main() -> int:
    key = get_settings().gemini_api_key
    if key is None:
        print("GEMINI_API_KEY is empty in .env")
        return 1

    embedder = Embedder(key.get_secret_value(), cache_path=QUERY_CACHE)
    collection = open_collection()  # refuses to open if model or size do not match
    keyword = load_keyword_index()
    by_id = {chunk["chunk_id"]: chunk for chunk in read_chunks()}

    for question in QUESTIONS:
        print("=" * 80)
        print(f"QUESTION: {question}")

        calls_before = embedder.stats["api_calls"]
        vector = embedder.embed_query(question)  # one API call, unless already cached

        print("\n  MEANING SEARCH (score = cosine similarity, higher is closer)")
        for rank, hit in enumerate(search_vectors(collection, vector, k=TOP_K), start=1):
            label = f"{hit['chunk_id']}  [{hit['service']}]  {hit['title']}"
            print(f"  {rank}. {hit['score']:.3f}  {label}")

        print("\n  WORD SEARCH (score = BM25, only chunks sharing a word)")
        word_hits = keyword.search(question, k=TOP_K)
        if not word_hits:
            print("  (no chunk shares a word with this question)")
        for rank, hit in enumerate(word_hits, start=1):
            chunk = by_id[hit["chunk_id"]]
            label = f"{hit['chunk_id']}  [{chunk['service']}]  {chunk['title']}"
            print(f"  {rank}. {hit['score']:.2f}  {label}")

        # Be gentle with the free tier: pause only if we really called the API.
        if embedder.stats["api_calls"] > calls_before:
            time.sleep(4)

    # ru_maxrss is the peak memory of this process, in kilobytes on Linux.
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print("=" * 80)
    print(f"peak memory of this script: {peak_mb:.0f} MB (laptop figure, not Render's)")
    print(f"API calls this run: {embedder.stats['api_calls']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
