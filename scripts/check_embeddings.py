"""Checking that the embedding model works with my key, and that Bangla and English match.

Run:  PYTHONPATH=src python scripts/check_embeddings.py
"""

import math
import sys
import time

import httpx

from app.config import get_settings

MODEL = "gemini-embedding-2"
DIMENSIONS = 768
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents"

# gemini-embedding-2 has no task_type setting. The task goes inside the text instead:
#   questions : "task: search result | query: <question>"
#   documents : "title: <title> | text: <passage>"   (use "title: none" if there is no title)
QUERY = "task: search result | query: ই-পাসপোর্টের ফি কত?"
DOCUMENTS = {
    "bangla fee page": "title: ই-পাসপোর্ট ফি | text: ই-পাসপোর্ট আবেদনের ফি এবং পেমেন্টের নিয়ম।",
    "english fee page": (
        "title: E-Passport Fees | text: Fees and payment options for the e-passport application."
    ),
    "unrelated (cake)": "title: none | text: How to bake a chocolate cake at home with flour.",
}


def norm(vector: list[float]) -> float:
    """Length of a vector."""
    return math.sqrt(sum(x * x for x in vector))


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity: close to 1 = similar meaning, close to 0 = unrelated."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (norm(a) * norm(b))


def embed(texts: list[str], api_key: str) -> list[list[float]]:
    """Embed every text separately: one request per text, sent together in one batch call."""
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
    response = httpx.post(URL, json=body, headers={"x-goog-api-key": api_key}, timeout=60)
    if response.status_code != 200:
        message = response.json().get("error", {}).get("message", response.text[:200])
        raise RuntimeError(f"HTTP {response.status_code}: {message}")
    return [item["values"] for item in response.json()["embeddings"]]


def main() -> int:
    key = get_settings().gemini_api_key
    if key is None:
        print("GEMINI_API_KEY is empty in .env")
        return 1
    texts = [QUERY, *DOCUMENTS.values()]
    started = time.time()
    try:
        vectors = embed(texts, key.get_secret_value())
    except RuntimeError as error:
        print(f"FAILED: {error}")
        return 1
    print(f"model: {MODEL} | took {time.time() - started:.1f}s")
    print(f"vectors returned: {len(vectors)} (expected {len(texts)})")
    print(f"vector length: {len(vectors[0])} (expected {DIMENSIONS})")
    print(f"vector norm: {norm(vectors[0]):.3f} (about 1.000 means normalized)")
    scores = {}
    for name, vector in zip(DOCUMENTS, vectors[1:], strict=True):
        scores[name] = cosine(vectors[0], vector)
        print(f"similarity to question | {name:18} | {scores[name]:.3f}")
    related = min(scores["bangla fee page"], scores["english fee page"])
    if scores["unrelated (cake)"] < related:
        print("PASS: both fee pages rank above the unrelated page")
        return 0
    print("CHECK: unexpected ranking, paste this output to Claude")
    return 1


if __name__ == "__main__":
    sys.exit(main())
