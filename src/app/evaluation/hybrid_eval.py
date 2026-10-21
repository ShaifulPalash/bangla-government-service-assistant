"""Compare retrieval variants: meaning only, words only, and hybrid with different weights.

Run:   PYTHONPATH=src python -m app.evaluation.hybrid_eval [--split dev|test|all]

Uses the same questions, labels and scoring as retrieval_eval, so the numbers are directly
comparable. Question vectors come from the cache, so a repeat run makes no API calls.
"""

from __future__ import annotations

import json
import sys

from app.config import get_settings
from app.evaluation.dataset import EvalQuestion, load_dataset
from app.evaluation.metrics import retrieval_questions
from app.evaluation.retrieval_eval import RESULTS_DIR, TOP_K, evaluate, table
from app.indexing.embeddings import CACHE_FILE
from app.indexing.vector_index import IndexMismatchError
from app.retrieval.hybrid import build_retriever

# (name, mode, weights)
VARIANTS = [
    ("meaning", "meaning", None),
    ("word", "word", None),
    ("hybrid 1:1", "hybrid", {"meaning": 1.0, "word": 1.0}),
    ("hybrid 2:1", "hybrid", {"meaning": 2.0, "word": 1.0}),
    ("hybrid 3:1", "hybrid", {"meaning": 3.0, "word": 1.0}),
]


def run_variants(questions: list[EvalQuestion], retriever, variants=VARIANTS, k: int = TOP_K):
    """results[variant][question_id] = ranked chunks, for every question that tests retrieval."""
    scored = retrieval_questions(questions)
    return {
        name: {
            q.id: retriever.retrieve(q.question, k=k, mode=mode, weights=weights) for q in scored
        }
        for name, mode, weights in variants
    }


def rank_table(report: dict) -> list[str]:
    """One line per question: where each variant ranked the expected document."""
    names = list(report["methods"])
    lines = ["question  " + "  ".join(f"{name:>10}" for name in names)]
    rows_by_name = {name: report["methods"][name]["rows"] for name in names}
    for index, row in enumerate(rows_by_name[names[0]]):
        ranks = [rows_by_name[name][index]["doc_rank"] for name in names]
        cells = "  ".join(f"{'-' if rank is None else rank:>10}" for rank in ranks)
        lines.append(f"{row['question'].id}      {cells}")
    return lines


def format_comparison(report: dict, split: str) -> str:
    methods = report["methods"]
    lines = [
        f"Retrieval variants | split: {split} | {report['n_questions']} questions | top {TOP_K}"
    ]
    lines += ["", *table("document level", {m: d["overall"] for m, d in methods.items()})]
    for key, title in (("by_language", "by language"), ("by_service", "by service")):
        groups = sorted({g for d in methods.values() for g in d[key]})
        summaries = {f"{g} / {m}": d[key][g] for g in groups for m, d in methods.items()}
        lines += ["", *table(title, summaries)]
    lines += ["", "Rank of the expected document per question ('-' = not in the top 10):"]
    lines += rank_table(report)
    return "\n".join(lines)


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
        retriever = build_retriever(key.get_secret_value(), cache_path=CACHE_FILE)
        questions = [q for q in load_dataset() if split in ("all", q.split)]
    except (FileNotFoundError, IndexMismatchError) as error:
        print(error)
        return 1
    results = run_variants(questions, retriever)
    report = evaluate(questions, results)
    print(format_comparison(report, split))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"variants-{split}.json"
    payload = {
        "split": split,
        "top_k": TOP_K,
        "variants": {name: data["overall"] for name, data in report["methods"].items()},
        "per_question": {
            name: {row["question"].id: row["doc_rank"] for row in data["rows"]}
            for name, data in report["methods"].items()
        },
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsaved: eval/results/{out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
