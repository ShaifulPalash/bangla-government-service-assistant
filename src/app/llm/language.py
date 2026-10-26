"""Guess the language of a question: Bangla script, Bangla typed in English letters, or English."""

from __future__ import annotations

import re

# Common Bangla words as people type them in English letters ("Banglish").
BANGLISH_WORDS = frozenset(
    {
        "ami", "amar", "amake", "apni", "apnar", "tumi", "ki", "kivabe", "kibhabe", "kemon",
        "keno", "kothay", "kothaye", "koto", "kon", "kar", "ta", "ti", "er", "jonno", "lagbe",
        "lage", "hobe", "hoy", "korbo", "korte", "kora", "kore", "korun", "dibo", "debo",
        "pabo", "pete", "paben", "ache", "achhe", "nei", "nai", "hariye", "haraye", "gele",
        "geche", "gechhe", "chai", "dorkar", "kagoj", "kagojpotro", "ekta", "theke", "jante",
        "janate", "bolun", "kobe", "kotodin",
    }
)  # fmt: skip

# Common English words. Banglish text almost never contains them.
ENGLISH_WORDS = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "do", "does", "did", "i", "my", "me", "we", "you",
        "your", "how", "what", "which", "when", "where", "why", "can", "could", "should", "would",
        "will", "to", "for", "of", "in", "on", "at", "and", "or", "if", "it", "this", "that", "be",
        "have", "has", "need", "get", "much", "many",
    }
)  # fmt: skip


def detect_language(text: str) -> str:
    """Return "bn" (Bangla script), "bn-latn" (Bangla in English letters) or "en"."""
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return "en"
    bangla = sum("\u0980" <= char <= "\u09ff" for char in letters)
    if bangla / len(letters) >= 0.3:
        return "bn"
    words = re.findall(r"[a-z]+", text.lower())
    banglish = sum(word in BANGLISH_WORDS for word in words)
    english = sum(word in ENGLISH_WORDS for word in words)
    return "bn-latn" if banglish > english else "en"


def answer_language(language: str) -> str:
    """The language name we put in the prompt. Bangla questions get Bangla-script answers."""
    return "English" if language == "en" else "Bangla (written in Bangla script)"
