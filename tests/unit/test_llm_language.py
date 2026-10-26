import pytest

from app.evaluation.dataset import load_dataset
from app.llm.language import answer_language, detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ই-পাসপোর্টের ফি কত?", "bn"),
        ("ই-passport এর ফি কত?", "bn"),
        ("How do I pay my electricity bill?", "en"),
        ("What documents do I need?", "en"),
        ("NID card hariye gele ki korbo?", "bn-latn"),
        ("amar gas er bill koto, kivabe dibo?", "bn-latn"),
        ("", "en"),
        ("12345", "en"),
    ],
)
def test_language_examples(text, expected):
    assert detect_language(text) == expected


def test_answer_language_names():
    assert answer_language("en") == "English"
    assert "Bangla script" in answer_language("bn")
    assert "Bangla script" in answer_language("bn-latn")


def test_detector_agrees_with_every_labelled_question_in_the_dataset():
    wrong = [
        (q.id, q.language, detect_language(q.question))
        for q in load_dataset()
        if detect_language(q.question) != q.language
    ]
    assert wrong == []
