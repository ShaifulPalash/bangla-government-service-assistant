"""Display helpers that make Bangla answers fully Bangla: digits, taka amounts, dates.

They change only HOW a number is shown, never its value. The API has already checked every
number against the sources, and the digit mapping is one-to-one, so 4,025 becomes ৪,০২৫ and
nothing else changes. There is no Streamlit code here, so it is easy to test.
"""

from __future__ import annotations

import re
from datetime import date

_TO_BANGLA = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

_BANGLA_MONTHS = (
    "জানুয়ারি",
    "ফেব্রুয়ারি",
    "মার্চ",
    "এপ্রিল",
    "মে",
    "জুন",
    "জুলাই",
    "আগস্ট",
    "সেপ্টেম্বর",
    "অক্টোবর",
    "নভেম্বর",
    "ডিসেম্বর",
)
_ENGLISH_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# "TK 4,025" or "BDT 4,025.50" becomes "4,025 টাকা". The amount keeps its exact digits.
# The number pattern stops before a trailing comma, so "TK 4,025, express" stays correct.
_TAKA = re.compile(r"\b(?:TK|BDT)\.?\s*(\d+(?:,\d+)*(?:\.\d+)?)", re.IGNORECASE)


def is_bangla(language: str) -> bool:
    """True for a Bangla question, in Bangla script ("bn") or English letters ("bn-latn")."""
    return language in ("bn", "bn-latn")


def bangla_digits(text: str) -> str:
    return text.translate(_TO_BANGLA)


def localize_answer(text: str, language: str) -> str:
    """The answer text with taka amounts, digits and list numbers in Bangla."""
    if not is_bangla(language):
        return text
    text = _TAKA.sub(lambda match: f"{match.group(1)} টাকা", text)
    # Bangla list numbers are no longer a Markdown list, so keep each line on its own line.
    return bangla_digits(text).replace("\n", "  \n")


def format_date(value: str, language: str) -> str:
    """'2026-07-12' becomes '12 July 2026' or '১২ জুলাই ২০২৬'."""
    try:
        day = date.fromisoformat(str(value)[:10])
    except ValueError:
        return bangla_digits(str(value)) if is_bangla(language) else str(value)
    if is_bangla(language):
        return bangla_digits(f"{day.day} {_BANGLA_MONTHS[day.month - 1]} {day.year}")
    return f"{day.day} {_ENGLISH_MONTHS[day.month - 1]} {day.year}"


def format_marks(numbers: list[int], language: str) -> str:
    """Citation marks such as [1], [2], matching the marks inside the answer."""
    marks = ", ".join(f"[{number}]" for number in numbers)
    return bangla_digits(marks) if is_bangla(language) else marks


def format_page(page: int | str, language: str) -> str:
    return f"পৃ. {bangla_digits(str(page))}" if is_bangla(language) else f"p. {page}"
