"""Safety checks that run BEFORE any language-model call.

1. Personal numbers (NID, passport, phone) are replaced with placeholders, so they are never
   sent to a model provider and never written to a log. Free-tier providers may use prompts
   to improve their products, so this matters.
2. Attempts to override the rules ("ignore your rules", "show your system prompt") are refused.
3. Requests for another person's data ("the NID number of my neighbour") are refused.

These are pattern rules. They catch common phrasings, not every clever one. The prompt's
rule 7 is the second layer of defence. The patterns are kept narrow on purpose so ordinary
questions are not blocked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Bangla digits to ASCII digits. Both have the same length, so positions stay the same.
_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# ---- 1. Personal numbers -------------------------------------------------------------------
# Listed in priority order: if two patterns match the same text, the first one wins.
_NUMBER_PATTERNS = [
    # Bangladesh mobile number: 01XXXXXXXXX or +8801XXXXXXXXX
    ("PHONE_NUMBER", re.compile(r"(?<!\d)(?:\+?880|0)1[3-9]\d{8}(?!\d)")),
    # NID numbers have 10 digits (smart card) or 13 / 17 digits (older cards)
    ("NID_NUMBER", re.compile(r"(?<!\d)(?:\d{17}|\d{13}|\d{10})(?!\d)")),
    # Passport number: one or two letters followed by 7 or 8 digits, like A01234567
    ("PASSPORT_NUMBER", re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,2}\d{7,8}(?![A-Za-z0-9])")),
]


def redact_personal_numbers(text: str) -> tuple[str, list[str]]:
    """Replace personal numbers with placeholders. Returns (clean text, kinds found)."""
    folded = text.translate(_DIGITS)  # so ১২৩৪৫৬৭৮৯০ is found like 1234567890
    found = []
    for priority, (kind, pattern) in enumerate(_NUMBER_PATTERNS):
        for match in pattern.finditer(folded):
            found.append((match.start(), -match.end(), priority, kind))
    found.sort()  # earliest first; at the same start the longer match, then the priority

    pieces, position, kinds = [], 0, []
    for start, negative_end, _priority, kind in found:
        if start < position:
            continue  # overlaps a match we already replaced
        pieces.append(text[position:start])  # slices come from the ORIGINAL text
        pieces.append(f"[{kind}]")
        position = -negative_end
        kinds.append(kind)
    pieces.append(text[position:])
    return "".join(pieces), kinds


# ---- 2. Instruction override ---------------------------------------------------------------
_INJECTION_PATTERNS = [
    re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+|any\s+)?(?:of\s+)?"
        r"(?:the\s+)?(?:your|my|previous|prior|above|earlier|these|those|system)\s+"
        r"(?:\w+\s+){0,2}?(?:rules?|instructions?|prompts?|guidelines?|restrictions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|show|print|repeat|display|leak)\s+(?:me\s+)?"
        r"(?:your\s+(?:system\s+|hidden\s+|initial\s+|secret\s+)?"
        r"|the\s+(?:system|hidden|initial|secret)\s+)(?:prompt|instructions?|rules)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bsystem\s+prompt\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\s+(?:a|an|my|in)\b", re.IGNORECASE),
    re.compile(r"\bpretend\s+(?:to\s+be|you\s+are)\b", re.IGNORECASE),
    re.compile(r"\b(?:developer\s+mode|jailbreak)\b", re.IGNORECASE),
    re.compile(r"\bignore\s+koro\b|\bbhule\s+jao\b", re.IGNORECASE),  # Banglish
]
_INJECTION_BANGLA = ("নিয়ম উপেক্ষা", "নির্দেশ উপেক্ষা", "নির্দেশনা উপেক্ষা", "সিস্টেম প্রম্পট")


def looks_like_instruction_override(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS) or any(
        phrase in text for phrase in _INJECTION_BANGLA
    )


# ---- 3. Someone else's data ----------------------------------------------------------------
_OTHERS_DATA_PATTERNS = [
    # "NID number of my neighbour", "passport details of Rahim" (but not "of me / of my own")
    re.compile(
        r"\b(?:nid|passport|national\s+id)(?:\s+card)?\s*"
        r"(?:numbers?|no\.?|details|info(?:rmation)?|data|records?)\s+of\s+"
        r"(?!me\b|my\s+own\b|myself\b)",
        re.IGNORECASE,
    ),
    # "someone's NID", "my neighbour's passport"
    re.compile(
        r"\b(?:someone|somebody|neighbou?r|stranger|another\s+person|other\s+person)"
        r"(?:['’]s|s['’])?\s+(?:nid|passport|national\s+id|address|phone|number)\b",
        re.IGNORECASE,
    ),
    # "find a person by NID", "look up someone's name"
    re.compile(
        r"\b(?:look\s*up|find|search|check)\s+(?:for\s+)?(?:a\s+)?"
        r"(?:person|people|someone|somebody|anyone)\b.{0,30}\b(?:nid|passport|name|number)\b",
        re.IGNORECASE,
    ),
    # Bangla: "প্রতিবেশীর এনআইডি", "অন্যের পাসপোর্ট নম্বর"
    re.compile(
        r"(?:প্রতিবেশী|অন্যের|অন্য কারো|অন্য কারও|কারো|কারও).{0,25}"
        r"(?:এনআইডি|পাসপোর্ট|নম্বর|ঠিকানা|ফোন)"
    ),
]


def asks_for_other_peoples_data(text: str) -> bool:
    return any(p.search(text) for p in _OTHERS_DATA_PATTERNS)


# ---- Putting the three checks together -------------------------------------------------------
@dataclass(frozen=True)
class SafetyResult:
    question: str  # the question with personal numbers already replaced
    redacted: list[str]  # kinds of numbers that were replaced, for example ["NID_NUMBER"]
    blocked_reason: str | None  # None, "instruction_override" or "others_data"

    @property
    def blocked(self) -> bool:
        return self.blocked_reason is not None


def safety_check(question: str) -> SafetyResult:
    """Run all checks. Use result.question from here on, never the original text."""
    clean, kinds = redact_personal_numbers(question)
    reason = None
    if looks_like_instruction_override(clean):
        reason = "instruction_override"
    elif asks_for_other_peoples_data(clean):
        reason = "others_data"
    return SafetyResult(question=clean, redacted=kinds, blocked_reason=reason)


# ---- Fixed messages (no model call needed) ---------------------------------------------------
PRIVACY_NOTICE = {
    "en": "Please do not type your NID, passport or phone number here. "
    "I removed it from your message before processing.",
    "bn": "দয়া করে এখানে আপনার এনআইডি, পাসপোর্ট বা ফোন নম্বর লিখবেন না। "
    "প্রক্রিয়া করার আগে আমি এটি আপনার বার্তা থেকে সরিয়ে দিয়েছি।",
}

BLOCK_MESSAGES = {
    "instruction_override": {
        "en": "I can only answer questions about Bangladesh passport and NID services, "
        "using official documents. I can't change or reveal how I work.",
        "bn": "আমি শুধু সরকারি নথির ভিত্তিতে বাংলাদেশের পাসপোর্ট ও এনআইডি সেবা বিষয়ক প্রশ্নের "
        "উত্তর দিতে পারি। আমি আমার কাজের নিয়ম বদলাতে বা প্রকাশ করতে পারি না।",
    },
    "others_data": {
        "en": "I can't share personal information about other people. I can only explain "
        "how passport and NID services work.",
        "bn": "আমি অন্য কারও ব্যক্তিগত তথ্য দিতে পারি না। আমি শুধু পাসপোর্ট ও এনআইডি সেবার নিয়ম ব্যাখ্যা করতে পারি।",
    },
}


def message_for(key: str, language: str) -> str:
    """The fixed message for a block reason (or 'privacy'), in 'en' or Bangla ('bn')."""
    table = PRIVACY_NOTICE if key == "privacy" else BLOCK_MESSAGES[key]
    return table["en" if language == "en" else "bn"]
