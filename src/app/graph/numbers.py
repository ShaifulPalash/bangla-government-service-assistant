"""Check that the numbers in an answer really come from the passages it was based on.

A wrong fee is the worst mistake this assistant can make. If a number in the answer
appears nowhere in the sources, the answer is not shown.
"""

import re

_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
# Citation markers like [1], [১, ২] or 【1】 are not numbers in the answer.
_CITATION = re.compile(r"\[\s*[\d০-৯]+(?:\s*[,،]\s*[\d০-৯]+)*\s*\]|【[^】]*】")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    """Numbers in a text as plain strings: Bangla digits become ASCII, commas are removed."""
    folded = _CITATION.sub(" ", text).translate(_DIGITS)
    return {match.group().rstrip(",").replace(",", "") for match in _NUMBER.finditer(folded)}


def unsupported_numbers(answer: str, passages: list[dict]) -> list[str]:
    """Numbers (two or more digits) in the answer that no passage or source date contains."""
    allowed: set[str] = set()
    for passage in passages:
        for field in ("text", "title", "last_updated_date", "verified_date"):
            allowed |= numbers_in(str(passage.get(field) or ""))
        allowed |= numbers_in(str(passage.get("page") or ""))
    return sorted(
        number
        for number in numbers_in(answer)
        if len(number.replace(".", "")) >= 2 and number not in allowed
    )
