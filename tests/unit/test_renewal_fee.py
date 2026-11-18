"""Tests for detecting a question about the fee for renewing or re-issuing a passport."""

import pytest

from app.graph.routing import asks_renewal_fee


@pytest.mark.parametrize(
    "question",
    [
        "What is the passport renewal fee?",
        "passport renew fee koto?",
        "passport re-issue fee koto?",
        "passport reissue fee koto?",
        "How much does it cost to renew my passport?",
        "passport renew korte koto taka lagbe?",
        "পাসপোর্ট রিনিউ ফি কত?",
        "পাসপোর্ট পুনঃইস্যু ফি কত?",
        "পাসপোর্ট নবায়নের খরচ কত?",
    ],
)
def test_renewal_fee_questions_are_detected(question):
    assert asks_renewal_fee(question, "passport") is True


@pytest.mark.parametrize(
    "question",
    [
        "What documents do I need for passport re-issue?",
        "How long does passport renewal take?",
        "How much is the passport fee?",
        "পাসপোর্ট ফি কত?",
    ],
)
def test_other_questions_are_not(question):
    assert asks_renewal_fee(question, "passport") is False


def test_only_passport_questions_count():
    assert asks_renewal_fee("What is the NID renewal fee?", "nid") is False
    assert asks_renewal_fee("renewal fee", "unclear") is False
