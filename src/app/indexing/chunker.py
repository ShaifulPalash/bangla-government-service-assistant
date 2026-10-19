"""Cut cleaned documents into small passages (chunks) for search.

Rules:
- A chunk never crosses a page boundary, so every chunk has exactly one page number.
- We prefer to cut at paragraph breaks, then line breaks, then sentence ends
  (including the Bangla dari "।"), then spaces.
- Neighbouring chunks overlap a little, so an answer cut in half can still be found.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCUMENTS_FILE = PROJECT_ROOT / "data" / "processed" / "documents.jsonl"
CHUNKS_FILE = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"

MAX_CHARS = 1000  # biggest chunk, in characters
OVERLAP_CHARS = 150  # how much of the previous chunk is repeated at the start of the next
MIN_CHARS = 25  # shorter leftovers are noise (for example a lone page number)

# Where we are willing to cut, best first. The dari "।" ends Bangla sentences.
SEPARATORS = ["\n\n", "\n", "। ", ". ", "? ", "! ", "; ", " "]

# Document fields copied onto every chunk.
CARRIED_FIELDS = (
    "title",
    "url",
    "service",
    "language",
    "publisher",
    "last_updated_date",
    "verified_date",
    "extraction",
)


def _split(text: str, max_chars: int, separators: list[str]) -> list[str]:
    """Break text into pieces no longer than max_chars, cutting at the best separator."""
    if len(text) <= max_chars:
        return [text]
    if not separators:  # last resort: no separator left, cut by length
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
    separator, rest = separators[0], separators[1:]
    parts = text.split(separator)
    pieces: list[str] = []
    for index, part in enumerate(parts):
        piece = part + (separator if index < len(parts) - 1 else "")
        if not piece:
            continue
        if len(piece) <= max_chars:
            pieces.append(piece)
        else:
            pieces.extend(_split(piece, max_chars, rest))
    return pieces


def _overlap_tail(text: str, overlap: int) -> str:
    """The last few characters of a chunk, starting at a word boundary."""
    if overlap <= 0 or len(text) <= overlap * 2:
        return ""
    tail = text[-overlap:]
    match = re.search(r"\s", tail)
    return tail[match.end() :] if match else ""


def split_text(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Cut one block of text into overlapping chunks of at most max_chars characters."""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    for piece in _split(text, max_chars, SEPARATORS):
        if current and len(current) + len(piece) > max_chars:
            chunks.append(current.strip())
            carried = _overlap_tail(current, overlap)
            current = carried + piece if len(carried) + len(piece) <= max_chars else piece
        else:
            current += piece
    if current.strip():
        chunks.append(current.strip())
    return [chunk for chunk in chunks if len(chunk) >= MIN_CHARS or len(chunks) == 1]


def build_chunks(document: dict) -> list[dict]:
    """Turn one document record into chunk records. Chunks never cross page boundaries."""
    chunks: list[dict] = []
    for page in document["pages"]:
        page_number = page["page"]
        label = f"p{page_number:03d}" if page_number is not None else "p000"
        for index, text in enumerate(split_text(page["text"])):
            chunk = {
                "chunk_id": f"{document['id']}-{label}-c{index:02d}",
                "doc_id": document["id"],
                "page": page_number,
            }
            chunk.update({field: document.get(field) for field in CARRIED_FIELDS})
            chunk["text"] = text
            chunk["char_count"] = len(text)
            chunks.append(chunk)
    return chunks


def main() -> int:
    """Chunk every document in documents.jsonl, write chunks.jsonl, print a size report."""
    if not DOCUMENTS_FILE.exists():
        print("documents.jsonl not found. Run: make build-documents")
        return 1
    chunks: list[dict] = []
    print(f"{'doc':8} {'chunks':>6} {'min':>5} {'avg':>5} {'max':>5}")
    with DOCUMENTS_FILE.open(encoding="utf-8") as file:
        for line in file:
            document = json.loads(line)
            doc_chunks = build_chunks(document)
            chunks.extend(doc_chunks)
            sizes = [chunk["char_count"] for chunk in doc_chunks] or [0]
            average = sum(sizes) // len(sizes)
            row = (len(doc_chunks), min(sizes), average, max(sizes))
            print(f"{document['id']:8} {row[0]:>6} {row[1]:>5} {row[2]:>5} {row[3]:>5}")
    ids = [chunk["chunk_id"] for chunk in chunks]
    if len(ids) != len(set(ids)):
        print("ERROR: duplicate chunk ids")
        return 1
    with CHUNKS_FILE.open("w", encoding="utf-8") as file:
        for chunk in chunks:
            file.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"\n{len(chunks)} chunks -> {CHUNKS_FILE.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
