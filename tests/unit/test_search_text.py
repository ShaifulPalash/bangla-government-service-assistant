"""Tests for the search text used to find passages."""

import pytest

from app.graph.routing import INSIDE_BANGLADESH_HINT, search_text


@pytest.mark.parametrize(
    "question",
    ["Tell me about passport fee", "How much does an e-passport cost?", "পাসপোর্ট ফি কত?"],
)
def test_passport_fee_questions_get_the_hint(question):
    assert search_text(question, "passport") == f"{question} ({INSIDE_BANGLADESH_HINT})"


@pytest.mark.parametrize(
    "question",
    [
        "What is the passport fee for labors abroad?",
        "e-passport fee in USD",
        "বিদেশে পাসপোর্টের ফি কত?",
        "fee for a student at a Bangladesh mission",
    ],
)
def test_questions_about_other_groups_are_unchanged(question):
    assert search_text(question, "passport") == question


def test_other_questions_and_services_are_unchanged():
    assert (
        search_text("How long does a passport take?", "passport")
        == "How long does a passport take?"
    )
    assert (
        search_text("What is the NID correction fee?", "nid") == "What is the NID correction fee?"
    )
    assert search_text("ফিঙ্গারপ্রিন্ট দিয়ে কী যাচাই হয়?", "passport") == "ফিঙ্গারপ্রিন্ট দিয়ে কী যাচাই হয়?"
