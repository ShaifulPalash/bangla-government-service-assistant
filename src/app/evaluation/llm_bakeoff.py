"""Compare language models on real questions with real retrieved passages.

Run:  PYTHONPATH=src python -m app.evaluation.llm_bakeoff
      [--questions q001,q002] [--models gemini,groq] [--groq-effort low|medium|none]

Every model gets the same passages and the same prompt. The checks that a computer can do are
printed (valid JSON, right decision, citations, invented numbers, language). The Bangla
answers are for you to read.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections.abc import Callable

from app.config import Settings, get_settings
from app.evaluation.dataset import EvalQuestion, load_dataset
from app.evaluation.retrieval_eval import RESULTS_DIR
from app.indexing.embeddings import CACHE_FILE
from app.indexing.vector_index import IndexMismatchError
from app.ingest.text_cleaning import fold_digits
from app.llm.prompts import (
    SYSTEM_PROMPT,
    ParsedAnswer,
    build_user_prompt,
    format_sources,
    parse_answer,
)
from app.llm.providers import GeminiClient, GroqClient, LLMError
from app.retrieval.hybrid import build_retriever

# Six answerable questions, two out-of-scope (one is a prompt-injection attempt),
# one ambiguous, and the "current NID fee" question.
DEFAULT_QUESTIONS = ("q001", "q002", "q003", "q006", "q010", "q013", "q019", "q022", "q024", "q028")
TOP_K = 3  # passages given to the model
GEMINI_GAP_SECONDS = 4.0  # pause between calls, to stay under unknown free limits
GROQ_MIN_GAP_SECONDS = 2.0
GROQ_TOKENS_PER_MINUTE = 6000  # a safe margin under the 8,000 free limit

_CITATION = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_NUMBER = re.compile(r"\d[\d,]*\d|\d")


def numbers_in(text: str) -> set[str]:
    """Numbers of two or more digits. Bangla digits are converted, [1]-style citations skipped."""
    cleaned = _CITATION.sub(" ", fold_digits(text))
    found = {match.replace(",", "") for match in _NUMBER.findall(cleaned)}
    return {number for number in found if len(number) >= 2}


def invented_numbers(answer: str, evidence: str) -> list[str]:
    """Numbers the answer states that do not appear anywhere in the sources it was given."""
    return sorted(numbers_in(answer) - numbers_in(evidence))


def bangla_ratio(text: str) -> float:
    """Share of the letters that are Bangla."""
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum("\u0980" <= char <= "\u09ff" for char in letters) / len(letters)


def language_ok(question_language: str, answer: str) -> bool:
    """Bangla questions should get Bangla answers, English questions English answers."""
    ratio = bangla_ratio(answer)
    return ratio >= 0.4 if question_language in ("bn", "bn-latn") else ratio <= 0.1


def check_answer(
    question: EvalQuestion, parsed: ParsedAnswer, evidence: str, n_passages: int
) -> dict:
    """The automatic checks for one answer."""
    expected = question.expected_behavior == "answer"
    cited_ok = True
    if parsed.can_answer:
        cited_ok = bool(parsed.sources) and all(1 <= n <= n_passages for n in parsed.sources)
    return {
        "json_ok": parsed.can_answer is not None,
        "can_answer": parsed.can_answer,
        "expected_can_answer": expected,
        "behavior_ok": parsed.can_answer is expected,
        "cited_ok": cited_ok,
        "invented_numbers": invented_numbers(parsed.answer, evidence),
        "language_ok": language_ok(question.language, parsed.answer),
    }


def pause_for(provider: str, result) -> float:
    """How long to wait before the next call to the same provider."""
    if provider == "groq":
        tokens = (result.prompt_tokens or 0) + (result.output_tokens or 0)
        return max(GROQ_MIN_GAP_SECONDS, tokens / GROQ_TOKENS_PER_MINUTE * 60)
    return GEMINI_GAP_SECONDS


def run_bakeoff(
    questions: list[EvalQuestion],
    retriever,
    candidates: dict[str, object],
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """One row per (question, model)."""
    rows: list[dict] = []
    for question in questions:
        passages = retriever.retrieve(question.question, k=TOP_K, mode="meaning")
        user = build_user_prompt(question.question, passages)
        evidence = format_sources(passages)
        for label, client in candidates.items():
            row: dict = {"question_id": question.id, "language": question.language, "model": label}
            try:
                result = client.generate(SYSTEM_PROMPT, user)
            except LLMError as error:
                row["error"] = str(error)
                rows.append(row)
                sleep(GEMINI_GAP_SECONDS)
                continue
            parsed = parse_answer(result.text)
            row.update(check_answer(question, parsed, evidence, len(passages)))
            row.update(
                {
                    "answer": parsed.answer,
                    "sources": parsed.sources,
                    "latency_ms": result.latency_ms,
                    "prompt_tokens": result.prompt_tokens,
                    "output_tokens": result.output_tokens,
                }
            )
            rows.append(row)
            sleep(pause_for(client.provider, result))
    return rows


def summarize(rows: list[dict]) -> dict[str, dict]:
    """Totals per model."""
    summary: dict[str, dict] = {}
    for model in dict.fromkeys(row["model"] for row in rows):
        mine = [row for row in rows if row["model"] == model]
        answered = [row for row in mine if "error" not in row]

        def average(key: str, answered=answered) -> float | None:
            values = [row[key] for row in answered if row.get(key) is not None]
            return sum(values) / len(values) if values else None

        summary[model] = {
            "questions": len(mine),
            "errors": len(mine) - len(answered),
            "json_ok": sum(row["json_ok"] for row in answered),
            "behavior_ok": sum(row["behavior_ok"] for row in answered),
            "cited_ok": sum(row["cited_ok"] for row in answered),
            "with_invented_numbers": sum(bool(row["invented_numbers"]) for row in answered),
            "language_ok": sum(row["language_ok"] for row in answered),
            "avg_latency_ms": average("latency_ms"),
            "avg_prompt_tokens": average("prompt_tokens"),
            "avg_output_tokens": average("output_tokens"),
        }
    return summary


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def format_summary(summary: dict[str, dict]) -> list[str]:
    lines = [
        f"{'model':<24}{'errors':>7}{'json':>6}{'decision':>9}{'cited':>7}{'bad-nums':>9}"
        f"{'language':>9}{'ms':>7}{'tok-in':>8}{'tok-out':>8}"
    ]
    for model, s in summary.items():
        n = s["questions"]
        lines.append(
            f"{model:<24}{s['errors']:>7}{s['json_ok']:>4}/{n:<2}{s['behavior_ok']:>6}/{n:<2}"
            f"{s['cited_ok']:>4}/{n:<2}{s['with_invented_numbers']:>7}  "
            f"{s['language_ok']:>6}/{n:<2}{_fmt(s['avg_latency_ms']):>6}"
            f"{_fmt(s['avg_prompt_tokens']):>8}{_fmt(s['avg_output_tokens']):>8}"
        )
    return lines


def format_answers(rows: list[dict], questions: list[EvalQuestion]) -> list[str]:
    lines = []
    for question in questions:
        lines += ["", f"{question.id} [{question.language}] expected: {question.expected_behavior}"]
        lines.append(f"  Q: {question.question}")
        for row in (r for r in rows if r["question_id"] == question.id):
            if "error" in row:
                lines.append(f"  - {row['model']}: ERROR {row['error'][:150]}")
                continue
            flags = []
            if not row["behavior_ok"]:
                flags.append("WRONG DECISION")
            if row["invented_numbers"]:
                flags.append(f"INVENTED {row['invented_numbers']}")
            if not row["cited_ok"]:
                flags.append("BAD CITATION")
            if not row["language_ok"]:
                flags.append("WRONG LANGUAGE")
            flag_text = f"  <-- {', '.join(flags)}" if flags else ""
            lines.append(
                f"  - {row['model']} | can_answer={row['can_answer']} sources={row['sources']} "
                f"{row['latency_ms']}ms{flag_text}"
            )
            lines.append(f"      {' '.join(row['answer'].split())[:400]}")
    return lines


def build_candidates(settings: Settings, groq_effort: str | None, only: list[str]) -> dict:
    """The models to compare. `only` keeps names that contain one of its words."""
    candidates: dict[str, object] = {}
    if settings.gemini_api_key:
        key = settings.gemini_api_key.get_secret_value()
        candidates["gemini-3.8-flash"] = GeminiClient(key, "gemini-3.8-flash")
        candidates["gemini-3.5-flash-lite"] = GeminiClient(key, "gemini-3.5-flash-lite")
    if settings.groq_api_key:
        key = settings.groq_api_key.get_secret_value()
        candidates["groq gpt-oss-120b"] = GroqClient(
            key, "openai/gpt-oss-120b", reasoning_effort=groq_effort
        )
    if only:
        candidates = {n: c for n, c in candidates.items() if any(word in n for word in only)}
    return candidates


def option(argv: list[str], name: str, default: str) -> str:
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv: list[str]) -> int:
    settings = get_settings()
    if settings.gemini_api_key is None:
        print("GEMINI_API_KEY is empty in .env (needed to search)")
        return 1
    wanted = option(argv, "--questions", ",".join(DEFAULT_QUESTIONS)).split(",")
    effort = option(argv, "--groq-effort", "low")
    only = [word for word in option(argv, "--models", "").split(",") if word]
    candidates = build_candidates(settings, None if effort == "none" else effort, only)
    if not candidates:
        print("no model to test (check the keys in .env and the --models option)")
        return 1
    try:
        retriever = build_retriever(settings.gemini_api_key.get_secret_value(), CACHE_FILE)
    except (FileNotFoundError, IndexMismatchError) as error:
        print(error)
        return 1
    by_id = {q.id: q for q in load_dataset()}
    questions = [by_id[qid] for qid in wanted if qid in by_id]

    print(
        f"LLM bake-off | {len(questions)} questions x {len(candidates)} models | {TOP_K} passages"
    )
    print("(this takes a few minutes: the calls are spaced out to respect the free limits)")

    def show_progress(seconds: float) -> None:
        print(".", end="", flush=True)  # one dot per finished call
        time.sleep(seconds)

    rows = run_bakeoff(questions, retriever, candidates, show_progress)
    print()
    summary = summarize(rows)
    print()
    print("\n".join(format_summary(summary)))
    print("\n".join(format_answers(rows, questions)))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "llm-bakeoff.json"
    out.write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nsaved: eval/results/{out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
