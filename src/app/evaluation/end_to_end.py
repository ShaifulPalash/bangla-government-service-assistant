"""End-to-end evaluation: real search, real language models, labelled questions.

For every question we compare what the assistant DID (answer, clarify or refuse) with what
the label says it SHOULD do, and also check the cited documents and the answer language.

Usage:
  PYTHONPATH=src python -m app.evaluation.end_to_end                 # dev split (for tuning)
  PYTHONPATH=src python -m app.evaluation.end_to_end --split test    # final evaluation only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter

from app.evaluation.dataset import PROJECT_ROOT, EvalQuestion, load_dataset
from app.llm.language import detect_language

QUERY_CACHE = PROJECT_ROOT / "data" / "processed" / "query_cache.jsonl"
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
MODEL_PAUSE = 15.0  # seconds after a question that called a language model (token limit)
OTHER_PAUSE = 2.0  # seconds after the others (be gentle with the embedding limit)


def judge(question: EvalQuestion, result: dict) -> dict:
    """Compare one result with its label."""
    decision = result["decision"]
    cited = sorted({c["doc_id"] for c in result["citations"]})
    citation_ok = None  # only meaningful for answers to questions that have expected documents
    if decision == "answer" and question.expected_docs:
        citation_ok = bool(set(cited) & set(question.expected_docs))
    answer_language = "en" if detect_language(result["message"]) == "en" else "bn"
    wanted_language = "en" if question.language == "en" else "bn"
    return {
        "id": question.id,
        "type": question.type,
        "split": question.split,
        "question": question.question,
        "expected": question.expected_behavior,
        "decision": decision,
        "reason": result["reason"],
        "behavior_ok": decision == question.expected_behavior,
        "cited_docs": cited,
        "expected_docs": question.expected_docs,
        "citation_ok": citation_ok,
        "language_ok": answer_language == wanted_language,
        "top_score": result["top_score"],
        "provider": result["provider"],
        "path": result["path"],
        "message": result["message"],
    }


def rate(hits: int, total: int) -> float | None:
    return None if total == 0 else round(hits / total, 3)


def summarize(rows: list[dict]) -> dict:
    """The numbers for the report."""
    refused = [r for r in rows if r["decision"] == "refuse"]
    should_refuse = [r for r in rows if r["expected"] == "refuse"]
    citable = [r for r in rows if r["citation_ok"] is not None]
    confusion: dict[str, Counter] = {"answer": Counter(), "clarify": Counter(), "refuse": Counter()}
    for row in rows:
        confusion[row["expected"]][row["decision"]] += 1
    return {
        "questions": len(rows),
        "decision_accuracy": rate(sum(r["behavior_ok"] for r in rows), len(rows)),
        "refusal_precision": rate(sum(r["expected"] == "refuse" for r in refused), len(refused)),
        "refusal_recall": rate(
            sum(r["decision"] == "refuse" for r in should_refuse), len(should_refuse)
        ),
        "citation_accuracy": rate(sum(r["citation_ok"] for r in citable), len(citable)),
        "language_accuracy": rate(sum(r["language_ok"] for r in rows), len(rows)),
        "unavailable": sum(r["decision"] == "unavailable" for r in rows),
        "confusion": {expected: dict(counts) for expected, counts in confusion.items()},
    }


def format_summary(summary: dict, split: str) -> str:
    def show(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.2f}"

    lines = [
        f"End-to-end evaluation | split: {split} | {summary['questions']} questions",
        f"  decision accuracy  {show(summary['decision_accuracy'])}",
        f"  refusal precision  {show(summary['refusal_precision'])}",
        f"  refusal recall     {show(summary['refusal_recall'])}",
        f"  citation accuracy  {show(summary['citation_accuracy'])}",
        f"  language accuracy  {show(summary['language_accuracy'])}",
        f"  unavailable        {summary['unavailable']}",
        "  expected -> what the assistant did:",
    ]
    for expected, counts in summary["confusion"].items():
        lines.append(f"    {expected:8} {counts}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="End-to-end evaluation.")
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args(argv)

    # Heavy imports live here so the unit tests of judge() and summarize() stay fast.
    from app.config import get_settings
    from app.graph.workflow import ask, build_graph
    from app.llm.providers import LLMError, build_chain
    from app.retrieval.hybrid import build_retriever

    settings = get_settings()
    if settings.gemini_api_key is None:
        print("GEMINI_API_KEY is empty in .env (it is needed for the search)")
        return 1
    try:
        chain = build_chain(settings)
    except LLMError as error:
        print(error)
        return 1
    retriever = build_retriever(settings.gemini_api_key.get_secret_value(), QUERY_CACHE)
    graph = build_graph(retriever, chain)

    questions = [q for q in load_dataset() if q.split == args.split]
    print(f"{len(questions)} questions | split {args.split} | calls are paced for the free limits")
    rows = []
    for question in questions:
        result = ask(graph, question.question)
        row = judge(question, result)
        rows.append(row)
        flag = "ok  " if row["behavior_ok"] else "MISS"
        print(
            f"{flag} {row['id']} expected {row['expected']:8} got {row['decision']:11} "
            f"({row['reason']}) {row['provider'] or '-'}"
        )
        time.sleep(MODEL_PAUSE if result["provider"] else OTHER_PAUSE)

    summary = summarize(rows)
    print()
    print(format_summary(summary, args.split))
    for row in rows:
        problems = []
        if not row["behavior_ok"]:
            problems.append(f"expected {row['expected']}, got {row['decision']} ({row['reason']})")
        if row["citation_ok"] is False:
            problems.append(f"cited {row['cited_docs']}, expected one of {row['expected_docs']}")
        if not row["language_ok"]:
            problems.append("wrong answer language")
        if problems:
            print(f"\n{row['id']}: {row['question']}")
            print("   " + "; ".join(problems))
            print("   " + row["message"][:200].replace("\n", " "))

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"e2e-{args.split}.json"
    report = {"split": args.split, "summary": summary, "rows": rows}
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved: {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
