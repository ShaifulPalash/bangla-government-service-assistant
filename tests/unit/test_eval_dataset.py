import json

import pytest
from pydantic import ValidationError

from app.evaluation.dataset import (
    DatasetError,
    EvalQuestion,
    check_dataset,
    contains_phrase,
    load_dataset,
    summarize,
)


def make_question(**overrides) -> dict:
    question = {
        "id": "q001",
        "question": "What is the passport fee?",
        "language": "en",
        "type": "answerable",
        "expected_behavior": "answer",
        "expected_docs": ["ppt-002"],
        "evidence": ["fee 1200 taka"],
        "split": "dev",
    }
    question.update(overrides)
    return question


def parse(**overrides) -> EvalQuestion:
    return EvalQuestion.model_validate(make_question(**overrides))


def test_a_good_answerable_question_is_accepted():
    assert parse().id == "q001"


def test_bad_id_is_rejected():
    with pytest.raises(ValidationError):
        parse(id="x1")


def test_answerable_question_needs_expected_docs():
    with pytest.raises(ValidationError, match="expected_docs"):
        parse(expected_docs=[])


def test_out_of_scope_must_refuse_and_have_no_docs():
    with pytest.raises(ValidationError, match="refuse"):
        parse(type="out_of_scope", expected_behavior="answer", expected_docs=[])
    with pytest.raises(ValidationError, match="no expected_docs"):
        parse(type="out_of_scope", expected_behavior="refuse")


def test_ambiguous_must_ask_for_clarification():
    with pytest.raises(ValidationError, match="clarify"):
        parse(type="ambiguous", expected_behavior="answer", expected_docs=[])


def test_outdated_question_needs_notes():
    with pytest.raises(ValidationError, match="notes"):
        parse(type="outdated", expected_behavior="refuse")
    assert parse(type="outdated", expected_behavior="refuse", notes="2015 notice only").notes


def test_duplicates_and_unknown_documents_are_reported():
    first = parse()
    second = parse(question="what is the passport fee")  # same words, different punctuation
    third = parse(id="q002", question="Another one", expected_docs=["zzz-999"])
    problems = check_dataset([first, second, third], known_doc_ids={"ppt-002"})
    text = " | ".join(problems)
    assert "duplicate id" in text
    assert "same question text" in text
    assert "unknown document 'zzz-999'" in text


def test_strict_mode_requires_evidence_for_answerable_questions():
    question = parse(evidence=[])
    assert check_dataset([question], {"ppt-002"}) == []
    assert "evidence" in check_dataset([question], {"ppt-002"}, strict=True)[0]


def test_strict_mode_checks_that_evidence_really_is_in_the_document():
    texts = {"ppt-002": "The fee is 1200 taka for ten years."}
    good = parse(evidence=["fee is 1200 taka"])
    bad = parse(evidence=["fee is 9999 taka"])
    assert check_dataset([good], {"ppt-002"}, texts, strict=True) == []
    assert "not found" in check_dataset([bad], {"ppt-002"}, texts, strict=True)[0]


def test_phrase_matching_ignores_punctuation_case_and_digit_script():
    assert contains_phrase("ফি ১২০০ টাকা। অন্যান্য তথ্য", "ফি 1200 টাকা")
    assert contains_phrase("The Fee,\nis 1200 Taka.", "fee is 1200 taka")
    assert not contains_phrase("passport fees", "passport fee")  # whole words only


def test_load_dataset_names_the_bad_line_and_skips_blank_lines(tmp_path):
    path = tmp_path / "dataset.jsonl"
    good = json.dumps(make_question(), ensure_ascii=False)
    bad = json.dumps(make_question(id="q002", expected_docs=[]))
    path.write_text(good + "\n\n" + bad + "\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="line 3"):
        load_dataset(path)
    path.write_text(good + "\n\n", encoding="utf-8")
    assert len(load_dataset(path)) == 1


def test_summary_counts_by_service_and_type():
    questions = [
        parse(),
        parse(id="q002", question="Lost card?", expected_docs=["nid-001"]),
        parse(
            id="q003",
            question="Electricity bill?",
            type="out_of_scope",
            expected_behavior="refuse",
            expected_docs=[],
            evidence=[],
        ),
    ]
    summary = summarize(questions)
    assert summary["service"] == {"passport": 1, "nid": 1, "none": 1}
    assert summary["type"] == {"answerable": 2, "out_of_scope": 1}
