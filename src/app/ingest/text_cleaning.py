"""Text cleaning helpers for Bangla and English government documents."""

from __future__ import annotations

import re
import unicodedata

# Bangla digits to ASCII digits. Used for scanning and, later, for search.
BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Invisible characters that are never part of a correct word:
# zero-width space, byte-order mark, soft hyphen, direction marks, word joiner.
# We deliberately KEEP U+200C and U+200D (ZWNJ and ZWJ): correct Bangla spelling needs them.
INVISIBLE_CHARS = dict.fromkeys(map(ord, "\u200b\ufeff\u00ad\u200e\u200f\u2060"))

# Lines at the top of our saved files that describe the file, not the document.
HEADER_PREFIXES = (
    "source:",
    "source url:",
    "url:",
    "document:",
    "language:",
    "page language:",
    "pages:",
    "verification:",
    "section:",
    "title:",
    "captured on:",
    "page last updated:",
)
HEADER_SCAN_LINES = 15

# Matches page markers such as "--- Page 2 ---".
PAGE_MARKER = re.compile(r"^\s*-{2,}\s*Page\s+(\d+)\s*-{2,}\s*$", re.IGNORECASE | re.MULTILINE)

# Patterns for personal-data warnings (run after Bangla digits are converted).
PHONE = re.compile(r"(?<!\d)(?:\+?880[\s-]?|0)1[3-9]\d{2}[\s-]?\d{6}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LONG_NUMBER = re.compile(r"(?<!\d)(?:\d{10}|\d{13}|\d{17})(?!\d)")  # NID-length numbers


def fold_digits(text: str) -> str:
    """Convert Bangla digits (০-৯) to ASCII digits (0-9)."""
    return text.translate(BANGLA_DIGITS)


def normalize_text(text: str) -> str:
    """Make text consistent: Unicode NFC, no invisible junk, tidy whitespace."""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(INVISIBLE_CHARS)
    text = text.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_header(text: str) -> str:
    """Remove file-description lines (Source:, URL:, ...) near the top of a saved file."""
    kept = []
    for index, line in enumerate(text.split("\n")):
        if index < HEADER_SCAN_LINES and line.lstrip().lower().startswith(HEADER_PREFIXES):
            continue
        kept.append(line)
    return normalize_text("\n".join(kept))


def split_pages(text: str) -> list[tuple[int | None, str]]:
    """Split text on page markers. Returns (page_number, text). No markers gives page None."""
    parts = PAGE_MARKER.split(text)
    if len(parts) == 1:
        return [(None, text.strip())] if text.strip() else []
    pages: list[tuple[int | None, str]] = []
    preamble = parts[0].strip()
    if preamble:
        pages.append((None, preamble))
    for number, body in zip(parts[1::2], parts[2::2], strict=True):
        if body.strip():
            pages.append((int(number), body.strip()))
    return pages


def redact_phones(text: str) -> tuple[str, int]:
    """Replace mobile numbers with a placeholder. Returns (new_text, how_many)."""
    folded = fold_digits(text)  # same length as text, so positions line up
    pieces: list[str] = []
    last = 0
    count = 0
    for match in PHONE.finditer(folded):
        pieces.append(text[last : match.start()])
        pieces.append("[mobile number removed]")
        last = match.end()
        count += 1
    pieces.append(text[last:])
    return "".join(pieces), count


def scan_pii(text: str) -> dict[str, int]:
    """Count possible personal data. Only counts are returned, never the matched text."""
    folded = fold_digits(text)
    return {
        "phone": len(PHONE.findall(folded)),
        "email": len(EMAIL.findall(folded)),
        "long_number": len(LONG_NUMBER.findall(folded)),
    }
