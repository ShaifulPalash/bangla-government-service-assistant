"""Tokenizer for the BM25 keyword index.

BM25 matches words, so we cut text into word tokens. The same function
must be used for the documents and for the user's question.

Why not use the regex shortcut \\w? Python's \\w does not treat Bangla
vowel signs (া, ো, ু ...) as part of a word, so it breaks Bangla words
into pieces. Here we decide for each character ourselves.
"""

from __future__ import annotations

import unicodedata

# Translation table used with str.translate:
#   - Bangla digits ০-৯ become ASCII digits 0-9
#   - Zero-width non-joiner (U+200C) and joiner (U+200D) are deleted,
#     so a word typed with or without them gives the same tokens
_TRANSLATE_TABLE = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_TRANSLATE_TABLE.update({0x200C: None, 0x200D: None})


def _is_token_char(ch: str) -> bool:
    """Return True if the character can be part of a word.

    unicodedata.category gives a code like "Lo" (letter), "Mc"/"Mn"
    (combining mark, e.g. Bangla vowel signs) or "Nd" (digit).
    We keep Letters (L), Marks (M) and Numbers (N). Everything else
    (space, punctuation, danda "।") is a separator.
    """
    return unicodedata.category(ch)[0] in ("L", "M", "N")


def tokenize(text: str) -> list[str]:
    """Cut text into lowercase word tokens (works for Bangla and English)."""
    # NFC makes visually identical Bangla text use identical code points
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_TRANSLATE_TABLE).lower()

    tokens: list[str] = []
    current: list[str] = []
    for ch in text:
        if _is_token_char(ch):
            current.append(ch)
        elif current:
            # A separator ends the current word
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens
