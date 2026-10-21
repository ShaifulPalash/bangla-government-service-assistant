"""Retrieval metrics: hit rate and mean reciprocal rank (MRR).

A "rank" is the 1-based position of the first correct result, or None when there is no
correct result in the list we looked at. Everything here is a plain function with no
files and no network, so it is easy to test by hand.
"""

from __future__ import annotations

from collections.abc import Callable
from statistics import median

from app.evaluation.dataset import EvalQuestion, contains_phrase

KS = (1, 3, 5)


def retrieval_questions(questions: list[EvalQuestion]) -> list[EvalQuestion]:
    """The questions that test retrieval: they expect an answer from known documents."""
    return [q for q in questions if q.expected_behavior == "answer" and q.expected_docs]


def doc_rank(results: list[dict], expected_docs: list[str]) -> int | None:
    """Position of the first result that comes from an expected document."""
    for position, result in enumerate(results, start=1):
        if result["doc_id"] in expected_docs:
            return position
    return None


def passage_rank(results: list[dict], evidence: list[str]) -> int | None:
    """Position of the first result whose text contains one of the evidence phrases."""
    for position, result in enumerate(results, start=1):
        if any(contains_phrase(result["text"], phrase) for phrase in evidence):
            return position
    return None


def hit_at_k(rank: int | None, k: int) -> bool:
    """True if there is a correct result within the first k."""
    return rank is not None and rank <= k


def reciprocal_rank(rank: int | None) -> float:
    """1 for first place, 0.5 for second, and so on. 0 when there is no correct result."""
    return 0.0 if rank is None else 1.0 / rank


def summarize_ranks(ranks: list[int | None], ks: tuple[int, ...] = KS) -> dict:
    """Hit rate at each k and MRR for a list of ranks."""
    if not ranks:
        return {"n": 0, **{f"hit@{k}": None for k in ks}, "mrr": None}
    summary: dict = {"n": len(ranks)}
    for k in ks:
        summary[f"hit@{k}"] = sum(hit_at_k(rank, k) for rank in ranks) / len(ranks)
    summary["mrr"] = sum(reciprocal_rank(rank) for rank in ranks) / len(ranks)
    return summary


def score_question(results: list[dict], question: EvalQuestion) -> dict:
    """Both ranks for one question. passage_rank is None when no evidence is defined."""
    return {
        "question": question,
        "doc_rank": doc_rank(results, question.expected_docs),
        "passage_rank": passage_rank(results, question.evidence) if question.evidence else None,
    }


def ranks_of(rows: list[dict], field: str) -> list[int | None]:
    """The ranks of one kind. Passage ranks skip questions that have no evidence phrase."""
    return [row[field] for row in rows if field != "passage_rank" or row["question"].evidence]


def summarize_by(
    rows: list[dict], key: Callable[[EvalQuestion], str], field: str
) -> dict[str, dict]:
    """Summaries per group, for example per language or per service."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(key(row["question"]), []).append(row)
    return {name: summarize_ranks(ranks_of(group, field)) for name, group in sorted(groups.items())}


def score_stats(values: list[float]) -> dict:
    """Smallest, middle and largest of a list of scores (for example top similarity scores)."""
    if not values:
        return {"n": 0, "min": None, "median": None, "max": None}
    return {"n": len(values), "min": min(values), "median": median(values), "max": max(values)}
