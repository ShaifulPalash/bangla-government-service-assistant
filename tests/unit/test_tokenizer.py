"""Tests for the BM25 tokenizer."""

from app.indexing.tokenizer import tokenize


def test_english_is_lowercased_and_split():
    assert tokenize("How much is the Passport FEE?") == [
        "how",
        "much",
        "is",
        "the",
        "passport",
        "fee",
    ]


def test_bangla_words_stay_whole():
    # Vowel signs and the hasanta must NOT split a word
    assert tokenize("পাসপোর্ট ফি") == ["পাসপোর্ট", "ফি"]


def test_danda_and_question_mark_are_separators():
    assert tokenize("আবেদন করুন। ফি কত?") == ["আবেদন", "করুন", "ফি", "কত"]


def test_bangla_digits_become_ascii():
    assert tokenize("ফি ৫০০ টাকা") == ["ফি", "500", "টাকা"]
    assert tokenize("৫০০") == tokenize("500")


def test_zero_width_characters_are_removed():
    assert tokenize("ab\u200cc") == ["abc"]
    assert tokenize("a\u200db") == ["ab"]


def test_empty_and_punctuation_only_give_no_tokens():
    assert tokenize("") == []
    assert tokenize(" ।?! ") == []


def test_mixed_bangla_and_english():
    assert tokenize("NID কার্ড lost") == ["nid", "কার্ড", "lost"]


def test_hyphen_splits_words():
    assert tokenize("e-passport") == ["e", "passport"]
