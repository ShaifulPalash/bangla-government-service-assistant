"""Measure how well word search and meaning search find the right documents.

Run:   PYTHONPATH=src python -m app.evaluation.retrieval_eval [--split dev|test|all]

Needs make build-index done and GEMINI_API_KEY in .env (it embeds the questions).
Positions are counted in chunks, so the top 5 can contain several chunks of one document.
The test split is meant to stay untouched while you tune, so the default is dev.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.config import get_settings
from app.evaluation.dataset import EvalQuestion, load_dataset, service_of
from app.evaluation.metrics import (
    ranks_of,
    retrieval_questions,
    score_question,
    score_stats,
    summarize_by,
    summarize_ranks,
)
from app.indexing.embeddings import CACHE_FILE, Embedder, EmbeddingError, query_text
from app.indexing.keyword_index import load_keyword_index, read_chunks
from app.indexing.vector_index import IndexMismatchError, open_collection, search_vectors

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
TOP_K = 10
MISS_CUTOFF = 3  # a question is a "miss" if the right document is not in the top 3


def evaluate(questions: list[EvalQuestion], results: dict[str, dict[str, list[dict]]]) -> dict:
    """Score every retrieval question. results[method][question_id] is a ranked result list."""
    scored = retrieval_questions(questions)
    methods = {}
    for method, by_question in results.items():
        rows = [score_question(by_question[q.id], q) for q in scored]
        methods[method] = {
            "rows": rows,
            "overall": summarize_ranks(ranks_of(rows, "doc_rank")),
            "passage": summarize_ranks(ranks_of(rows, "passage_rank")),
            "by_language": summarize_by(rows, lambda q: q.language, "doc_rank"),
            "by_service": summarize_by(rows, service_of, "doc_rank"),
        }
    return {"n_questions": len(scored), "methods": methods}


def find_misses(report: dict, results: dict[str, dict[str, list[dict]]]) -> list[str]:
    """One line per (question, method) where the expected document is not in the top 3."""
    lines = []
    for method, data in report["methods"].items():
        for row in data["rows"]:
            question, rank = row["question"], row["doc_rank"]
            if rank is not None and rank <= MISS_CUTOFF:
                continue
            top = [hit["doc_id"] for hit in results[method][question.id][:MISS_CUTOFF]]
            found = f"rank {rank}" if rank else "not found"
            lines.append(
                f"{question.id} [{question.language}] {method}: expected "
                f"{question.expected_docs}, {found} | top {MISS_CUTOFF}: {top}"
            )
    return sorted(lines)


def top_scores_by_behavior(
    questions: list[EvalQuestion], meaning_results: dict[str, list[dict]]
) -> dict[str, dict]:
    """Top-1 meaning similarity grouped by what the assistant should do (answer/refuse/clarify)."""
    groups: dict[str, list[float]] = {}
    for question in questions:
        hits = meaning_results[question.id]
        if hits:
            groups.setdefault(question.expected_behavior, []).append(hits[0]["score"])
    return {name: score_stats(values) for name, values in sorted(groups.items())}


def top_score_rows(
    questions: list[EvalQuestion], meaning_results: dict[str, list[dict]]
) -> list[dict]:
    """Top-1 meaning similarity of every question, highest first."""
    rows = [
        {
            "id": q.id,
            "behavior": q.expected_behavior,
            "type": q.type,
            "score": meaning_results[q.id][0]["score"],
        }
        for q in questions
        if meaning_results[q.id]
    ]
    return sorted(rows, key=lambda row: row["score"], reverse=True)


def to_jsonable(report: dict) -> dict:
    """Same report without the question objects, so it can be saved as JSON."""
    methods = {}
    for method, data in report["methods"].items():
        methods[method] = {
            "overall": data["overall"],
            "passage": data["passage"],
            "by_language": data["by_language"],
            "by_service": data["by_service"],
            "per_question": {
                row["question"].id: {
                    "doc_rank": row["doc_rank"],
                    "passage_rank": row["passage_rank"],
                }
                for row in data["rows"]
            },
        }
    return {"n_questions": report["n_questions"], "methods": methods}


def number(value: float | None) -> str:
    return "  -  " if value is None else f"{value:5.2f}"


def table(title: str, summaries: dict[str, dict]) -> list[str]:
    """A small text table of hit rates and MRR."""
    lines = [f"{title:<26}{'n':>3}  hit@1 hit@3 hit@5   MRR"]
    for name, s in summaries.items():
        cells = " ".join(number(s[key]) for key in ("hit@1", "hit@3", "hit@5", "mrr"))
        lines.append(f"{name:<26}{s['n']:>3}  {cells}")
    return lines


def format_report(report: dict, split: str, stats: dict[str, dict]) -> str:
    methods = report["methods"]
    lines = [
        f"Retrieval baseline | split: {split} | {report['n_questions']} questions | top {TOP_K}"
    ]
    lines += ["", *table("document level", {m: d["overall"] for m, d in methods.items()})]
    lines += ["", *table("passage level (evidence)", {m: d["passage"] for m, d in methods.items()})]
    for key, title in (("by_language", "by language"), ("by_service", "by service")):
        groups = sorted({g for d in methods.values() for g in d[key]})
        summaries = {
            f"{g} / {m}": d[key][g] for g in groups for m, d in methods.items() if g in d[key]
        }
        lines += ["", *table(title, summaries)]
    lines += ["", "Top-1 meaning similarity by what the assistant should do:"]
    for name, s in stats.items():
        if s["n"]:
            lines.append(
                f"  {name:<8} n={s['n']:<3} min {s['min']:.2f}  median {s['median']:.2f}  "
                f"max {s['max']:.2f}"
            )
    return "\n".join(lines)


def run_searches(questions, embedder, collection, keyword_index, chunks) -> dict:
    """Search with both methods for every question."""
    vectors = embedder.embed([query_text(q.question) for q in questions])
    results: dict[str, dict[str, list[dict]]] = {"word": {}, "meaning": {}}
    for question, vector in zip(questions, vectors, strict=True):
        results["meaning"][question.id] = search_vectors(collection, vector, k=TOP_K)
        results["word"][question.id] = [
            {
                **hit,
                "doc_id": chunks[hit["chunk_id"]]["doc_id"],
                "text": chunks[hit["chunk_id"]]["text"],
            }
            for hit in keyword_index.search(question.question, k=TOP_K)
        ]
    return results


def main(argv: list[str]) -> int:
    split = argv[argv.index("--split") + 1] if "--split" in argv else "dev"
    if split not in ("dev", "test", "all"):
        print("--split must be dev, test or all")
        return 1
    key = get_settings().gemini_api_key
    if key is None:
        print("GEMINI_API_KEY is empty in .env")
        return 1
    try:
        collection = open_collection()
        keyword_index = load_keyword_index()
        questions = [q for q in load_dataset() if split in ("all", q.split)]
    except (FileNotFoundError, IndexMismatchError) as error:
        print(error)
        return 1
    chunks = {chunk["chunk_id"]: chunk for chunk in read_chunks()}
    embedder = Embedder(key.get_secret_value(), cache_path=CACHE_FILE)
    try:
        results = run_searches(questions, embedder, collection, keyword_index, chunks)
    except EmbeddingError as error:
        print(f"FAILED: {error}")
        return 1

    report = evaluate(questions, results)
    stats = top_scores_by_behavior(questions, results["meaning"])
    print(format_report(report, split, stats))
    rows = top_score_rows(questions, results["meaning"])
    print("\nTop-1 meaning similarity per question, highest first:")
    for row in rows:
        print(f"  {row['id']}  {row['behavior']:<8} {row['type']:<13} {row['score']:.2f}")
    misses = find_misses(report, results)
    print(f"\nMisses (expected document not in the top {MISS_CUTOFF}): {len(misses)}")
    for line in misses:
        print(f"  {line}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"retrieval-{split}.json"
    payload = {
        "split": split,
        "top_k": TOP_K,
        "report": to_jsonable(report),
        "top_scores": stats,
        "top_score_per_question": rows,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsaved: {out.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
