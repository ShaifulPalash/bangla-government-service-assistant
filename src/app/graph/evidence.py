"""Decide whether the retrieved passages are strong enough to answer from.

The number we compare is the best passage's cosine similarity (meaning search). The cut-off
was read off the dev-set scores in eval/results/retrieval-dev.json:
  weakest answerable question  q006  0.769
  strongest weak-evidence one  q027  0.741     (q028 is the known exception, see below)
  cut-off = midpoint = 0.755
If the embedding text changes (for example after removing the page boilerplate and
re-embedding), these scores move, and the cut-off must be recomputed.
"""

from __future__ import annotations

MIN_EVIDENCE_SCORE = 0.755


def best_score(passages: list[dict]) -> float:
    """The highest score among the passages, or 0.0 when there are none."""
    return max((p["score"] for p in passages), default=0.0)


def has_enough_evidence(passages: list[dict], threshold: float = MIN_EVIDENCE_SCORE) -> bool:
    """True when the best passage is similar enough to the question."""
    return best_score(passages) >= threshold
