"""Tests for the cheap routing rules."""

import pytest

from app.evaluation.dataset import load_dataset, service_of
from app.graph.routing import classify_service, is_out_of_scope_topic


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("পাসপোর্টের ফি কত?", "passport"),
        ("How do I renew my e-passport?", "passport"),
        ("NID card hariye gele ki korbo?", "nid"),
        ("এনআইডি সংশোধন করতে কী লাগবে?", "nid"),
        ("Can I use my NID and my passport together?", "both"),
        ("Can I use a gas bill as address proof for my passport?", "passport"),
        ("An unidentified person called me", "unclear"),
    ],
)
def test_classify_service_examples(question, expected):
    assert classify_service(question) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("How do I pay my electricity bill?", True),
        ("ড্রাইভিং লাইসেন্স নবায়নে কত টাকা লাগে?", True),
        ("How do I file my income tax return?", True),
        ("How much does it cost?", False),
    ],
)
def test_out_of_scope_examples(question, expected):
    assert is_out_of_scope_topic(question) is expected


def test_service_matches_every_labelled_question_with_documents():
    wrong = []
    for q in load_dataset():
        expected = service_of(q)
        if expected in ("passport", "nid") and classify_service(q.question) != expected:
            wrong.append(f"{q.id}: expected {expected}, got {classify_service(q.question)}")
    assert wrong == []


def test_ambiguous_questions_name_no_service_and_no_out_of_scope_topic():
    wrong = [
        q.id
        for q in load_dataset()
        if q.type == "ambiguous"
        and (classify_service(q.question) != "unclear" or is_out_of_scope_topic(q.question))
    ]
    assert wrong == []


def test_out_of_scope_questions_are_flagged():
    # q022 is a prompt-injection question that names the NID. The safety guard in
    # step 8.5 handles it, so it is checked on its own below.
    wrong = [
        q.id
        for q in load_dataset()
        if q.type == "out_of_scope"
        and q.id != "q022"
        and (classify_service(q.question) != "unclear" or not is_out_of_scope_topic(q.question))
    ]
    assert wrong == []


def test_injection_question_still_names_the_nid():
    question = next(q for q in load_dataset() if q.id == "q022")
    assert classify_service(question.question) == "nid"
