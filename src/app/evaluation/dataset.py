"""The labelled evaluation dataset: loading, checking and summarizing.

One question per line in eval/dataset.jsonl. Each question says what a good assistant
should do: answer (and from which documents), refuse, or ask a clarifying question.

Usage:
    python -m app.evaluation.dataset             check the file
    python -m app.evaluation.dataset --strict    also require evidence phrases that really
                                                 appear in the expected documents
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.indexing.tokenizer import tokenize
from app.ingest.sources import load_registry

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_FILE = PROJECT_ROOT / "eval" / "dataset.jsonl"
DOCUMENTS_FILE = PROJECT_ROOT / "data" / "processed" / "documents.jsonl"

SERVICE_BY_PREFIX = {"ppt": "passport", "nid": "nid"}


class DatasetError(ValueError):
    """Raised when the dataset file cannot be read."""


class EvalQuestion(BaseModel):
    """One labelled question."""

    id: str = Field(pattern=r"^q\d{3}$")
    question: str = Field(min_length=3)
    language: Literal["bn", "en", "bn-latn"]  # bn-latn = Bangla typed in English letters
    type: Literal["answerable", "out_of_scope", "ambiguous", "outdated"]
    expected_behavior: Literal["answer", "refuse", "clarify"]
    expected_docs: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)  # short phrases copied from the document
    split: Literal["dev", "test"]
    notes: str = ""

    @model_validator(mode="after")
    def check_rules_for_type(self) -> EvalQuestion:
        if self.type == "answerable":
            if self.expected_behavior != "answer":
                raise ValueError("an answerable question must expect 'answer'")
            if not self.expected_docs:
                raise ValueError("an answerable question needs expected_docs")
        elif self.type == "out_of_scope":
            if self.expected_behavior != "refuse":
                raise ValueError("an out_of_scope question must expect 'refuse'")
            if self.expected_docs:
                raise ValueError("an out_of_scope question must have no expected_docs")
        elif self.type == "ambiguous":
            if self.expected_behavior != "clarify":
                raise ValueError("an ambiguous question must expect 'clarify'")
            if self.expected_docs:
                raise ValueError("an ambiguous question must have no expected_docs")
        elif self.type == "outdated":
            if self.expected_behavior not in ("answer", "refuse"):
                raise ValueError("an outdated question must expect 'answer' or 'refuse'")
            if not self.expected_docs:
                raise ValueError("an outdated question needs expected_docs (the old documents)")
            if not self.notes.strip():
                raise ValueError("an outdated question needs notes that explain why")
        return self


def load_dataset(path: Path = DATASET_FILE) -> list[EvalQuestion]:
    """Read the JSONL file. A bad line raises DatasetError that names the line."""
    questions: list[EvalQuestion] = []
    with path.open(encoding="utf-8") as file:
        for number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                questions.append(EvalQuestion.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValidationError) as error:
                raise DatasetError(f"{path.name} line {number}: {error}") from error
    return questions


def load_doc_texts(path: Path = DOCUMENTS_FILE) -> dict[str, str]:
    """Full cleaned text of every document, by document id."""
    texts: dict[str, str] = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)
            texts[record["id"]] = "\n\n".join(page["text"] for page in record["pages"])
    return texts


def phrase_key(text: str) -> str:
    """The words of a text joined by single spaces.

    It ignores punctuation, line breaks, capital letters and the difference between
    Bangla and ASCII digits, so a copied phrase still matches.
    """
    return " ".join(tokenize(text))


def contains_phrase(text: str, phrase: str) -> bool:
    """True if the phrase appears in the text as whole words, in the same order."""
    return f" {phrase_key(phrase)} " in f" {phrase_key(text)} "


def check_dataset(
    questions: list[EvalQuestion],
    known_doc_ids: set[str],
    doc_texts: dict[str, str] | None = None,
    strict: bool = False,
) -> list[str]:
    """Return a list of problems (empty means the dataset is fine)."""
    problems: list[str] = []
    seen_ids: set[str] = set()
    seen_questions: set[str] = set()
    for question in questions:
        if question.id in seen_ids:
            problems.append(f"{question.id}: duplicate id")
        seen_ids.add(question.id)
        key = phrase_key(question.question)
        if key in seen_questions:
            problems.append(f"{question.id}: same question text as an earlier question")
        seen_questions.add(key)
        for doc_id in question.expected_docs:
            if doc_id not in known_doc_ids:
                problems.append(f"{question.id}: unknown document '{doc_id}'")
        if not strict:
            continue
        if question.type == "answerable" and not question.evidence:
            problems.append(f"{question.id}: needs at least one evidence phrase")
        if doc_texts is None:
            continue
        for phrase in question.evidence:
            if not any(
                contains_phrase(doc_texts.get(d, ""), phrase) for d in question.expected_docs
            ):
                problems.append(
                    f"{question.id}: evidence not found in the expected documents: {phrase[:40]!r}"
                )
    return problems


def service_of(question: EvalQuestion) -> str:
    """passport, nid, both, or none (for questions without expected documents)."""
    services = {SERVICE_BY_PREFIX.get(doc.split("-")[0], "?") for doc in question.expected_docs}
    if not services:
        return "none"
    return "both" if len(services) > 1 else next(iter(services))


def summarize(questions: list[EvalQuestion]) -> dict[str, dict[str, int]]:
    """Counts by type, language, split, expected behavior and service."""
    return {
        "type": dict(Counter(q.type for q in questions)),
        "language": dict(Counter(q.language for q in questions)),
        "split": dict(Counter(q.split for q in questions)),
        "behavior": dict(Counter(q.expected_behavior for q in questions)),
        "service": dict(Counter(service_of(q) for q in questions)),
    }


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    if not DATASET_FILE.exists():
        print("eval/dataset.jsonl not found yet.")
        return 1
    try:
        questions = load_dataset()
    except DatasetError as error:
        print(f"INVALID: {error}")
        return 1
    doc_texts = None
    if strict:
        if not DOCUMENTS_FILE.exists():
            print("documents.jsonl not found. Run: make build-documents")
            return 1
        doc_texts = load_doc_texts()
    known = {source.id for source in load_registry().sources}
    problems = check_dataset(questions, known, doc_texts, strict)
    mode = "strict" if strict else "basic"
    print(f"{len(questions)} questions | {mode} check | problems: {len(problems)}")
    for problem in problems:
        print(f"  - {problem}")
    for name, counts in summarize(questions).items():
        print(f"{name:9}: " + ", ".join(f"{key} {value}" for key, value in sorted(counts.items())))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
