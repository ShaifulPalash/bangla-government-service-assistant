"""Cheap routing rules: which service is a question about, and is its topic out of scope?

These are plain Python rules, not language-model calls. They cost no tokens, take
microseconds, and always give the same answer for the same question, so they are easy to test.

Bangla words get suffixes (পাসপোর্ট -> পাসপোর্টের), so for Bangla we look for the word
INSIDE the text. English words are matched as whole words, so "nid" does not match
inside "unidentified".
"""

from __future__ import annotations

import re

# Whole-word patterns for text typed in English letters (also covers Banglish).
PASSPORT_LATIN = re.compile(r"\b(?:e-?)?pass?ports?\b", re.IGNORECASE)
NID_LATIN = re.compile(r"\b(?:nid|voters?|national\s+id)\b", re.IGNORECASE)

# Bangla words, matched anywhere inside the text so suffixes do not matter.
PASSPORT_BANGLA = ("পাসপোর্ট",)
NID_BANGLA = ("এনআইডি", "জাতীয় পরিচয়", "ভোটার")

# Topics this project does NOT cover (tax and utilities were cut from the scope).
OUT_OF_SCOPE_LATIN = re.compile(
    r"\b(?:electricity|electric|bidyut|gas|water|wasa|bills?|tax|tin|driving|licen[cs]e)\b",
    re.IGNORECASE,
)
OUT_OF_SCOPE_BANGLA = (
    "বিদ্যুৎ",
    "গ্যাস",
    "পানি",
    "ট্যাক্স",
    "আয়কর",
    "ড্রাইভিং",
    "লাইসেন্স",
)


def mentions_passport(question: str) -> bool:
    return bool(PASSPORT_LATIN.search(question)) or any(w in question for w in PASSPORT_BANGLA)


def mentions_nid(question: str) -> bool:
    return bool(NID_LATIN.search(question)) or any(w in question for w in NID_BANGLA)


def classify_service(question: str) -> str:
    """Return "passport", "nid", "both" or "unclear" (no service is named)."""
    passport, nid = mentions_passport(question), mentions_nid(question)
    if passport and nid:
        return "both"
    if passport:
        return "passport"
    if nid:
        return "nid"
    return "unclear"


def is_out_of_scope_topic(question: str) -> bool:
    """True if the question names a topic we do not cover.

    The graph asks this ONLY when classify_service() says "unclear". If a service is
    named it wins: "can I use a gas bill as address proof for my passport?" is a
    passport question, not a gas question.
    """
    return bool(OUT_OF_SCOPE_LATIN.search(question)) or any(
        w in question for w in OUT_OF_SCOPE_BANGLA
    )


# Passport fee tables are separate for inside Bangladesh (TK) and Bangladesh missions (USD).
# Fee questions that do not mention missions or abroad are searched with the inside-Bangladesh
# heading added, so those rows rank first. Only the SEARCH text changes: the model still
# reads the visitor's own words.
_FEE_WORDS = re.compile(
    r"\b(?:fees?|cost|costs|price|prices|charges?|how much)\b"
    r"|(?<![\u0980-\u09ff])ফি(?![\u0980-\u09ff])|খরচ|মূল্য|টাকা",
    re.IGNORECASE,
)
_ABROAD_WORDS = re.compile(
    r"\b(?:abroad|overseas|mission|embassy|consulate|usd|dollars?|labou?rs?|students?|foreign)\b"
    r"|বিদেশ|মিশন|দূতাবাস|ডলার|শ্রমিক|ছাত্র|শিক্ষার্থী",
    re.IGNORECASE,
)
INSIDE_BANGLADESH_HINT = "Fee for inside Bangladesh (Including 15% VAT)"


def search_text(question: str, service: str) -> str:
    """The text used to find passages: the question, plus a hint for passport fee questions."""
    if service == "passport" and _FEE_WORDS.search(question) and not _ABROAD_WORDS.search(question):
        return f"{question} ({INSIDE_BANGLADESH_HINT})"
    return question
