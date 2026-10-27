"""Tests for the end-to-end judging and summary."""

from app.evaluation.dataset import EvalQuestion
from app.evaluation.end_to_end import judge, summarize


def question(kind="answerable", behavior="answer", docs=("ppt-002",), language="en"):
    return EvalQuestion(
        id="q001",
        question="How much is the fee?",
        language=language,
        type=kind,
        expected_behavior=behavior,
        expected_docs=list(docs),
        split="dev",
    )


def result(decision="answer", cited=("ppt-002",), message="The fee is TK 4,025."):
    return {
        "decision": decision,
        "reason": "ok",
        "citations": [{"doc_id": doc} for doc in cited],
        "message": message,
        "top_score": 0.8,
        "provider": "groq",
        "path": ["prepare"],
    }


def test_a_correct_cited_answer_passes_every_check():
    row = judge(question(), result())
    assert (row["behavior_ok"], row["citation_ok"], row["language_ok"]) == (True, True, True)


def test_citing_the_wrong_document_is_flagged():
    assert judge(question(), result(cited=("nid-001",)))["citation_ok"] is False


def test_refusing_an_answerable_question_is_a_miss():
    row = judge(question(), result(decision="refuse", cited=()))
    assert row["behavior_ok"] is False
    assert row["citation_ok"] is None


def test_english_answer_to_a_bangla_question_is_flagged():
    assert judge(question(language="bn"), result())["language_ok"] is False


def test_summary_numbers():
    refuse_label = question("out_of_scope", "refuse", ())
    rows = [
        judge(question(), result()),  # right
        judge(refuse_label, result("refuse", ())),  # right
        judge(refuse_label, result("answer", ())),  # should have refused
    ]
    summary = summarize(rows)
    assert summary["decision_accuracy"] == 0.667
    assert summary["refusal_precision"] == 1.0
    assert summary["refusal_recall"] == 0.5
    assert summary["citation_accuracy"] == 1.0
