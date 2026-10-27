"""Tests for the evidence check, including a replay of the dev-set scores."""

import json

import pytest

from app.evaluation.dataset import PROJECT_ROOT
from app.graph.evidence import MIN_EVIDENCE_SCORE, best_score, has_enough_evidence

RESULTS = PROJECT_ROOT / "eval" / "results" / "retrieval-dev.json"

SCORE_BLIND_SPOTS: set[str] = set()


def passages(*scores: float) -> list[dict]:
    return [{"score": score} for score in scores]


def test_no_passages_means_no_evidence():
    assert best_score([]) == 0.0
    assert has_enough_evidence([]) is False


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ((0.60, 0.80), True),  # the best passage decides, not the first or the average
        ((0.70, 0.74), False),
        ((MIN_EVIDENCE_SCORE,), True),  # exactly on the line counts as enough
    ],
)
def test_threshold_behaviour(scores, expected):
    assert has_enough_evidence(passages(*scores)) is expected


def load_rows() -> list[dict]:
    return json.loads(RESULTS.read_text(encoding="utf-8"))["top_score_per_question"]


def test_every_answerable_dev_question_passes():
    low = [
        row["id"]
        for row in load_rows()
        if row["behavior"] == "answer" and row["score"] < MIN_EVIDENCE_SCORE
    ]
    assert low == []


def test_weak_evidence_questions_fail_the_check():
    high = [
        row["id"]
        for row in load_rows()
        if row["behavior"] != "answer"
        and row["id"] not in SCORE_BLIND_SPOTS
        and row["score"] >= MIN_EVIDENCE_SCORE
    ]
    assert high == []


def test_the_margin_around_the_cutoff_is_still_wide_enough():
    rows = load_rows()
    weakest_answer = min(r["score"] for r in rows if r["behavior"] == "answer")
    strongest_other = max(
        r["score"] for r in rows if r["behavior"] != "answer" and r["id"] not in SCORE_BLIND_SPOTS
    )
    assert weakest_answer - strongest_other >= 0.02
