import pytest

from app.evaluation.dataset import EvalQuestion
from app.evaluation.metrics import (
    doc_rank,
    hit_at_k,
    passage_rank,
    reciprocal_rank,
    retrieval_questions,
    score_question,
    score_stats,
    summarize_by,
    summarize_ranks,
)


def make_question(**overrides) -> EvalQuestion:
    data = {
        "id": "q001",
        "question": "What is the fee?",
        "language": "en",
        "type": "answerable",
        "expected_behavior": "answer",
        "expected_docs": ["ppt-002"],
        "evidence": ["fee is 1200 taka"],
        "split": "dev",
    }
    data.update(overrides)
    return EvalQuestion.model_validate(data)


def results(*pairs: tuple[str, str]) -> list[dict]:
    return [{"doc_id": doc_id, "text": text} for doc_id, text in pairs]


def test_doc_rank_is_the_position_of_the_first_expected_document():
    found = results(("ppt-006", "a"), ("ppt-002", "b"), ("nid-001", "c"))
    assert doc_rank(found, ["ppt-002"]) == 2
    assert doc_rank(found, ["ppt-006", "ppt-002"]) == 1


def test_doc_rank_is_none_when_nothing_matches():
    assert doc_rank(results(("ppt-006", "a")), ["nid-001"]) is None
    assert doc_rank([], ["nid-001"]) is None


def test_passage_rank_looks_for_the_evidence_phrase_in_the_text():
    found = results(("ppt-002", "other text"), ("ppt-002", "Note: the Fee, is ১২০০ Taka."))
    assert passage_rank(found, ["fee is 1200 taka"]) == 2


def test_hit_at_k_boundaries():
    assert hit_at_k(3, 3) is True
    assert hit_at_k(3, 1) is False
    assert hit_at_k(None, 5) is False


def test_reciprocal_rank_values():
    assert reciprocal_rank(1) == 1.0
    assert reciprocal_rank(2) == 0.5
    assert reciprocal_rank(None) == 0.0


def test_summary_of_a_small_example_you_can_check_by_hand():
    summary = summarize_ranks([1, 2, None, 5])
    assert summary["n"] == 4
    assert summary["hit@1"] == pytest.approx(0.25)
    assert summary["hit@3"] == pytest.approx(0.5)
    assert summary["hit@5"] == pytest.approx(0.75)
    assert summary["mrr"] == pytest.approx((1 + 0.5 + 0 + 0.2) / 4)


def test_summary_of_nothing_is_not_a_division_by_zero():
    summary = summarize_ranks([])
    assert summary["n"] == 0
    assert summary["mrr"] is None


def test_score_question_has_no_passage_rank_without_evidence():
    question = make_question(evidence=[])
    row = score_question(results(("ppt-002", "x")), question)
    assert row["doc_rank"] == 1
    assert row["passage_rank"] is None


def test_summarize_by_groups_and_skips_questions_without_evidence_for_passages():
    with_evidence = score_question(
        results(("ppt-002", "the fee is 1200 taka")), make_question(language="en")
    )
    without_evidence = score_question(
        results(("ppt-002", "x")),
        make_question(id="q002", question="Other?", language="bn", evidence=[]),
    )
    rows = [with_evidence, without_evidence]
    by_language = summarize_by(rows, lambda q: q.language, "doc_rank")
    assert by_language["en"]["n"] == 1 and by_language["bn"]["n"] == 1
    passage_by_language = summarize_by(rows, lambda q: q.language, "passage_rank")
    assert passage_by_language["bn"]["n"] == 0
    assert passage_by_language["en"]["hit@1"] == 1.0


def test_only_answer_questions_with_documents_are_retrieval_questions():
    answer = make_question()
    refuse = make_question(
        id="q002",
        question="Bill?",
        type="out_of_scope",
        expected_behavior="refuse",
        expected_docs=[],
    )
    current_fee = make_question(
        id="q003", question="Fee now?", type="outdated", expected_behavior="refuse", notes="old"
    )
    assert retrieval_questions([answer, refuse, current_fee]) == [answer]


def test_score_stats():
    stats = score_stats([0.2, 0.9, 0.4])
    assert stats == {"n": 3, "min": 0.2, "median": 0.4, "max": 0.9}
    assert score_stats([])["n"] == 0
