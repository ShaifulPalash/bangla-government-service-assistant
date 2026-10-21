import json

from app.evaluation.dataset import EvalQuestion
from app.evaluation.retrieval_eval import (
    evaluate,
    find_misses,
    format_report,
    to_jsonable,
    top_score_rows,
    top_scores_by_behavior,
)


def make_question(qid: str, language: str = "en", docs=("ppt-002",), **overrides) -> EvalQuestion:
    data = {
        "id": qid,
        "question": f"Question {qid}?",
        "language": language,
        "type": "answerable",
        "expected_behavior": "answer",
        "expected_docs": list(docs),
        "evidence": [],
        "split": "dev",
    }
    data.update(overrides)
    return EvalQuestion.model_validate(data)


def hit(doc_id: str, score: float = 0.5) -> dict:
    return {"doc_id": doc_id, "text": "text", "score": score}


def fake_results():
    # q001: both methods find ppt-002 first. q002: word search misses it, meaning finds it 2nd.
    return {
        "word": {"q001": [hit("ppt-002")], "q002": [hit("nid-001"), hit("nid-003")]},
        "meaning": {"q001": [hit("ppt-002")], "q002": [hit("nid-001"), hit("ppt-002")]},
    }


def questions():
    return [make_question("q001"), make_question("q002", language="bn")]


def test_evaluate_scores_each_method_separately():
    report = evaluate(questions(), fake_results())
    assert report["n_questions"] == 2
    word, meaning = report["methods"]["word"], report["methods"]["meaning"]
    assert word["overall"]["hit@5"] == 0.5
    assert meaning["overall"]["hit@5"] == 1.0
    assert meaning["overall"]["mrr"] == 0.75  # (1 + 1/2) / 2
    assert meaning["by_language"]["bn"]["hit@1"] == 0.0
    assert meaning["by_language"]["en"]["hit@1"] == 1.0


def test_evaluate_ignores_questions_that_do_not_test_retrieval():
    refuse = make_question("q003", type="out_of_scope", expected_behavior="refuse", docs=())
    results = fake_results()
    results["word"]["q003"] = []
    results["meaning"]["q003"] = []
    report = evaluate([*questions(), refuse], results)
    assert report["n_questions"] == 2


def test_misses_name_the_question_method_and_what_was_found_instead():
    results = fake_results()
    report = evaluate(questions(), results)
    misses = find_misses(report, results)
    assert len(misses) == 1
    assert misses[0].startswith("q002 [bn] word: expected ['ppt-002'], not found")
    assert "nid-001" in misses[0]


def test_a_document_found_after_rank_three_is_also_a_miss():
    results = {
        "word": {"q001": [hit("a"), hit("b"), hit("c"), hit("ppt-002")]},
        "meaning": {"q001": [hit("ppt-002")]},
    }
    report = evaluate([make_question("q001")], results)
    misses = find_misses(report, results)
    assert len(misses) == 1
    assert "rank 4" in misses[0]


def test_top_scores_are_grouped_by_expected_behavior():
    refuse = make_question("q003", type="out_of_scope", expected_behavior="refuse", docs=())
    meaning = {"q001": [hit("x", 0.8)], "q002": [hit("x", 0.6)], "q003": [hit("x", 0.4)]}
    stats = top_scores_by_behavior([*questions(), refuse], meaning)
    assert stats["answer"]["n"] == 2
    assert stats["answer"]["median"] == 0.7
    assert stats["refuse"]["max"] == 0.4


def test_report_can_be_saved_as_json_and_printed():
    results = fake_results()
    report = evaluate(questions(), results)
    json.dumps(to_jsonable(report))  # must not raise
    stats = top_scores_by_behavior(questions(), {"q001": [hit("x")], "q002": [hit("x")]})
    text = format_report(report, "dev", stats)
    assert "document level" in text
    assert "bn / meaning" in text


def test_top_score_rows_are_listed_highest_first_with_their_behavior():
    refuse = make_question("q003", type="out_of_scope", expected_behavior="refuse", docs=())
    meaning = {
        "q001": [hit("x", 0.6)],
        "q002": [hit("x", 0.8)],
        "q003": [hit("x", 0.7)],
        "q004": [],
    }
    rows = top_score_rows([*questions(), refuse], meaning)
    assert [row["id"] for row in rows] == ["q002", "q003", "q001"]
    assert rows[1]["behavior"] == "refuse"
