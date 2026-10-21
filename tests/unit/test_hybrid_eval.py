from app.evaluation.dataset import EvalQuestion
from app.evaluation.hybrid_eval import VARIANTS, format_comparison, rank_table, run_variants
from app.evaluation.retrieval_eval import evaluate


def make_question(qid: str, language: str = "en") -> EvalQuestion:
    return EvalQuestion.model_validate(
        {
            "id": qid,
            "question": f"Question {qid}?",
            "language": language,
            "type": "answerable",
            "expected_behavior": "answer",
            "expected_docs": ["ppt-002"],
            "evidence": [],
            "split": "dev",
        }
    )


class FakeRetriever:
    """Meaning-style modes find the right document; word mode finds a wrong one."""

    def __init__(self):
        self.calls = []

    def retrieve(self, question, k, mode, weights):
        self.calls.append((mode, weights))
        doc_id = "nid-001" if mode == "word" else "ppt-002"
        return [{"doc_id": doc_id, "text": "text"}]


def test_every_variant_runs_for_every_retrieval_question():
    retriever = FakeRetriever()
    questions = [make_question("q001"), make_question("q002", language="bn")]
    results = run_variants(questions, retriever)
    assert list(results) == [name for name, _, _ in VARIANTS]
    assert len(retriever.calls) == len(VARIANTS) * 2
    assert set(results["meaning"]) == {"q001", "q002"}


def test_comparison_shows_each_variant_and_marks_missing_ranks():
    questions = [make_question("q001"), make_question("q002", language="bn")]
    results = run_variants(questions, FakeRetriever())
    report = evaluate(questions, results)
    assert report["methods"]["meaning"]["overall"]["hit@1"] == 1.0
    assert report["methods"]["word"]["overall"]["hit@1"] == 0.0
    lines = rank_table(report)
    assert lines[0].startswith("question")
    assert lines[1].split()[:3] == ["q001", "1", "-"]
    text = format_comparison(report, "dev")
    assert "hybrid 2:1" in text
    assert "bn / word" in text
