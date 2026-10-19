import pytest

from app.indexing.embeddings import DIMENSIONS
from app.indexing.vector_index import (
    IndexMismatchError,
    build_index,
    open_collection,
    search_vectors,
)


def vec(position: int) -> list[float]:
    """A vector with a single 1.0, so different positions are completely unrelated."""
    vector = [0.0] * DIMENSIONS
    vector[position] = 1.0
    return vector


def make_chunk(i: int, service: str = "nid", page: int | None = None) -> dict:
    return {
        "chunk_id": f"doc-p000-c0{i}",
        "doc_id": "doc",
        "page": page,
        "title": "Title",
        "url": "https://example.gov.bd/page",
        "service": service,
        "language": "bn",
        "publisher": "EC",
        "last_updated_date": None,
        "verified_date": "2026-10-15",
        "extraction": "web_text",
        "text": f"text {i}",
    }


def three_chunks():
    chunks = [make_chunk(0), make_chunk(1, page=3), make_chunk(2, service="passport")]
    return chunks, [vec(0), vec(1), vec(2)]


def test_search_returns_the_nearest_chunk_with_its_details(tmp_path):
    chunks, vectors = three_chunks()
    build_index(chunks, vectors, index_dir=tmp_path)
    hits = search_vectors(open_collection(tmp_path), vec(1), k=2)
    assert hits[0]["chunk_id"] == "doc-p000-c01"
    assert hits[0]["score"] == pytest.approx(1.0, abs=1e-3)
    assert hits[0]["page"] == 3
    assert hits[0]["url"] == "https://example.gov.bd/page"
    assert hits[0]["text"] == "text 1"
    assert hits[1]["score"] < 0.1


def test_chunks_without_a_page_come_back_with_page_none(tmp_path):
    chunks, vectors = three_chunks()
    build_index(chunks, vectors, index_dir=tmp_path)
    hits = search_vectors(open_collection(tmp_path), vec(0), k=1)
    assert hits[0]["page"] is None


def test_search_can_be_limited_to_one_service(tmp_path):
    chunks, vectors = three_chunks()
    build_index(chunks, vectors, index_dir=tmp_path)
    hits = search_vectors(open_collection(tmp_path), vec(1), k=3, service="passport")
    assert [hit["chunk_id"] for hit in hits] == ["doc-p000-c02"]


def test_index_refuses_to_open_with_a_different_model(tmp_path):
    chunks, vectors = three_chunks()
    build_index(chunks, vectors, index_dir=tmp_path, model="gemini-embedding-001")
    with pytest.raises(IndexMismatchError, match="Rebuild"):
        open_collection(tmp_path)


def test_build_rejects_vectors_of_the_wrong_size(tmp_path):
    with pytest.raises(ValueError, match="768"):
        build_index([make_chunk(0)], [[1.0, 2.0]], index_dir=tmp_path)


def test_rebuilding_replaces_the_old_index(tmp_path):
    chunks, vectors = three_chunks()
    build_index(chunks, vectors, index_dir=tmp_path)
    build_index(chunks[:2], vectors[:2], index_dir=tmp_path)
    assert open_collection(tmp_path).count() == 2


def test_opening_a_missing_index_gives_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="make build-vector-index"):
        open_collection(tmp_path / "nothing-here")
