"""Build the clean documents dataset: one record per source in documents.jsonl.

Each record keeps the source metadata, the cleaned text split into pages,
how the text was produced, and simple quality and privacy counters.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.ingest.sources import load_registry
from app.ingest.text_cleaning import redact_phones, scan_pii, split_pages, strip_header

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "documents.jsonl"

# How each final text was produced:
#   web_text      = text copied or downloaded from the live official web page
#   transcription = typed by hand from the original document
#   ocr_reviewed  = OCR text that the author corrected against the original PDF
FINAL_TEXT = {
    "ppt-001": ("data/raw/passport/ppt-001.txt", "web_text"),
    "ppt-002": ("data/raw/passport/ppt-002.txt", "web_text"),
    "ppt-003": ("data/raw/passport/ppt-003.txt", "web_text"),
    "ppt-004": ("data/raw/passport/ppt-004.txt", "web_text"),
    "ppt-005": ("data/raw/passport/ppt-005.txt", "web_text"),
    "ppt-006": ("data/raw/passport/ppt-006.txt", "web_text"),
    "nid-001": ("data/processed/nid/nid-001/transcription.txt", "transcription"),
    "nid-002": ("data/raw/nid/nid-002.txt", "web_text"),
    "nid-003": ("data/raw/nid/nid-003.txt", "web_text"),
    "nid-004": ("data/raw/nid/nid-004.txt", "web_text"),
    "nid-005": ("data/raw/nid/nid-005.txt", "web_text"),
    "nid-006": ("data/processed/nid/nid-006-fees.txt", "transcription"),
    "nid-007": ("data/processed/nid/nid-007/ocr.txt", "ocr_reviewed"),
    "nid-008": ("data/processed/nid/nid-008/ocr.txt", "ocr_reviewed"),
    "nid-009": ("data/processed/nid/nid-009/ocr.txt", "ocr_reviewed"),
    "nid-010": ("data/processed/nid/nid-010/ocr.txt", "ocr_reviewed"),
    "nid-011": ("data/processed/nid/nid-011/ocr.txt", "ocr_reviewed"),
}

# Sources whose contact lists name individual officers with personal mobile numbers.
# Mobile numbers are removed only here. Public helplines in other sources (such as the
# NID FAQ footer) are kept on purpose, and are still counted in pii_flags for review.
REDACT_PHONES_FOR = {"ppt-006"}

# Metadata copied from sources.yaml into every record.
KEEP_FIELDS = (
    "id",
    "title",
    "url",
    "service",
    "language",
    "publisher",
    "published_date",
    "last_updated_date",
    "verified_date",
    "notes",
)


def relative(path: Path) -> str:
    """Show a path relative to the project folder when possible."""
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def build_record(meta: dict, path: Path, extraction: str) -> dict:
    """Read one final text file and return its cleaned dataset record."""
    cleaned = strip_header(path.read_text(encoding="utf-8"))
    phones_removed = 0
    if meta.get("id") in REDACT_PHONES_FOR:
        cleaned, phones_removed = redact_phones(cleaned)
    pages = [{"page": number, "text": text} for number, text in split_pages(cleaned)]
    full_text = "\n\n".join(page["text"] for page in pages)
    record = {key: meta.get(key) for key in KEEP_FIELDS}
    record.update(
        {
            "extraction": extraction,
            "source_file": relative(path),
            "pages": pages,
            "char_count": len(full_text),
            "replacement_chars": full_text.count("\ufffd"),
            "phones_removed": phones_removed,
            "pii_flags": scan_pii(full_text),
        }
    )
    return record


def main() -> int:
    """Build documents.jsonl from the 17 final text files and print a quality report."""
    registry = load_registry()
    records: list[dict] = []
    problems: list[str] = []

    for source in registry.sources:
        if source.id not in FINAL_TEXT:
            problems.append(f"{source.id}: no final text file is chosen in FINAL_TEXT")
            continue
        relative_path, extraction = FINAL_TEXT[source.id]
        path = PROJECT_ROOT / relative_path
        if not path.exists() or path.stat().st_size == 0:
            problems.append(f"{source.id}: file missing or empty: {relative_path}")
            continue
        meta = source.model_dump(mode="json")
        records.append(build_record(meta, path, extraction))

    if problems:
        print("PROBLEMS (nothing was written):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"{'id':8} {'extraction':14} {'pages':>5} {'chars':>7} {'bad':>4} {'phones':>6}  pii")
    for record in records:
        pii = record["pii_flags"]
        pii_text = f"{pii['phone']}/{pii['email']}/{pii['long_number']}"
        print(
            f"{record['id']:8} {record['extraction']:14} {len(record['pages']):>5} "
            f"{record['char_count']:>7} {record['replacement_chars']:>4} "
            f"{record['phones_removed']:>6}  {pii_text}"
        )
    print("(bad = broken chars; phones = mobile numbers removed; pii = left over)")
    total_chars = sum(record["char_count"] for record in records)
    print(f"\n{len(records)} documents, {total_chars} characters -> {relative(OUTPUT_FILE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
