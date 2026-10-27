from app.evaluation.dataset import EvalQuestion
from app.evaluation.llm_bakeoff import (
    GEMINI_GAP_SECONDS,
    GROQ_MIN_GAP_SECONDS,
    bangla_ratio,
    check_answer,
    invented_numbers,
    language_ok,
    numbers_in,
    pause_for,
    run_bakeoff,
    summarize,
)
from app.llm.prompts import ParsedAnswer
from app.llm.providers import LLMError, LLMResult


def make_question(qid="q001", language="en", behavior="answer") -> EvalQuestion:
    answerable = behavior == "answer"
    return EvalQuestion.model_validate(
        {
            "id": qid,
            "question": f"Question {qid}?",
            "language": language,
            "type": "answerable" if answerable else "out_of_scope",
            "expected_behavior": behavior,
            "expected_docs": ["ppt-002"] if answerable else [],
            "evidence": [],
            "split": "dev",
        }
    )


def passages():
    return [
        {
            "chunk_id": "c1",
            "title": "Fees",
            "text": "Regular delivery: TK 4,025 for five years",
            "last_updated_date": "2026-07-12",
            "verified_date": "2026-10-14",
            "page": None,
        }
    ]


class FakeRetriever:
    def retrieve(self, question, k, mode):
        return passages()


class FakeClient:
    def __init__(self, provider, text=None, error=None):
        self.provider, self.text, self.error = provider, text, error

    def generate(self, system, user, max_output_tokens=800):
        if self.error:
            raise LLMError(self.error)
        return LLMResult(self.text, self.provider, "m", 100, 20, 250)


def test_numbers_ignore_citations_commas_and_single_digits():
    assert numbers_in("Fee TK 4,025 [1] and [1, 2], page 3, in 2026") == {"4025", "2026"}
    assert numbers_in("ফি ৪,০২৫ টাকা") == {"4025"}


def test_invented_numbers_are_those_missing_from_the_sources():
    evidence = "Regular delivery: TK 4,025 (updated 2026-07-12)"
    assert invented_numbers("The fee is TK 4,025 as of 2026-07-12.", evidence) == []
    assert invented_numbers("The fee is TK 5,750.", evidence) == ["5750"]


def test_language_check_for_bangla_and_english_answers():
    assert language_ok("bn", "ই-পাসপোর্টের ফি ৪,০২৫ টাকা")
    assert language_ok("bn-latn", "আবেদন করতে হবে")
    assert not language_ok("bn", "The fee is TK 4,025")
    assert language_ok("en", "The fee is TK 4,025")
    assert not language_ok("en", "আবেদন করতে হবে")
    assert bangla_ratio("123") == 0.0


def test_check_answer_marks_decision_citation_and_invented_numbers():
    evidence = "TK 4,025"
    good = check_answer(make_question(), ParsedAnswer(True, "TK 4,025 [1]", [1]), evidence, 1)
    assert good["behavior_ok"] and good["cited_ok"] and good["invented_numbers"] == []
    wrong = check_answer(make_question(), ParsedAnswer(False, "not found", []), evidence, 1)
    assert not wrong["behavior_ok"]
    uncited = check_answer(make_question(), ParsedAnswer(True, "TK 9,999", []), evidence, 1)
    assert not uncited["cited_ok"] and uncited["invented_numbers"] == ["9999"]
    out_of_range = check_answer(make_question(), ParsedAnswer(True, "x", [3]), evidence, 1)
    assert not out_of_range["cited_ok"]
    refusal = check_answer(
        make_question(behavior="refuse"), ParsedAnswer(False, "I cannot find it", []), evidence, 1
    )
    assert refusal["behavior_ok"] and refusal["cited_ok"]
    unreadable = check_answer(make_question(), ParsedAnswer(None, "text", []), evidence, 1)
    assert not unreadable["json_ok"] and not unreadable["behavior_ok"]


def test_pause_is_longer_for_groq_when_many_tokens_were_used():
    small = LLMResult("t", "groq", "m", 100, 20, 1)
    big = LLMResult("t", "groq", "m", 3000, 1000, 1)
    assert pause_for("groq", small) == GROQ_MIN_GAP_SECONDS
    assert pause_for("groq", big) == 4000 / 6000 * 60
    assert pause_for("gemini", big) == GEMINI_GAP_SECONDS


def test_bakeoff_makes_one_row_per_question_and_model_and_survives_errors():
    good = '{"can_answer": true, "answer": "TK 4,025 [1]", "sources": [1]}'
    candidates = {
        "model-a": FakeClient("gemini", good),
        "model-b": FakeClient("groq", error="HTTP 429"),
        "model-c": FakeClient("gemini", "plain text, not json"),
    }
    sleeps: list[float] = []
    rows = run_bakeoff(
        [make_question("q001"), make_question("q002")], FakeRetriever(), candidates, sleeps.append
    )
    assert len(rows) == 6
    by_model = {row["model"]: row for row in rows if row["question_id"] == "q001"}
    assert by_model["model-a"]["behavior_ok"] is True
    assert by_model["model-b"]["error"] == "HTTP 429"
    assert by_model["model-c"]["json_ok"] is False
    assert len(sleeps) == 6


def test_summary_counts_per_model():
    good = '{"can_answer": true, "answer": "TK 9,999 [1]", "sources": [1]}'
    rows = run_bakeoff(
        [make_question()],
        FakeRetriever(),
        {"a": FakeClient("gemini", good), "b": FakeClient("groq", error="down")},
        lambda s: None,
    )
    summary = summarize(rows)
    assert summary["a"]["with_invented_numbers"] == 1
    assert summary["a"]["behavior_ok"] == 1
    assert summary["b"]["errors"] == 1
    assert summary["b"]["avg_latency_ms"] is None
