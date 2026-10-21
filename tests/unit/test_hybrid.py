import pytest

from app.indexing.embeddings import DIMENSIONS
from app.indexing.keyword_index import build_keyword_index
from app.indexing.vector_index import build_index, open_collection
from app.retrieval.hybrid import Retriever, doc_id_of, reciprocal_rank_fusion


def vec(position: int) -> list[float]:
    vector = [0.0] * DIMENSIONS
    vector[position] = 1.0
    return vector


def make_chunk(i: int, doc_id: str, service: str, title: str, text: str) -> dict:
    return {
        "chunk_id": f"{doc_id}-p000-c0{i}",
        "doc_id": doc_id,
        "page": None,
        "title": title,
        "url": f"https://example.gov.bd/{doc_id}",
        "service": service,
        "language": "en",
        "publisher": "DIP",
        "last_updated_date": None,
        "verified_date": "2026-10-15",
        "extraction": "web_text",
        "text": text,
    }


CHUNKS = [
    make_chunk(0, "ppt-002", "passport", "E-Passport Fees", "e-passport fee payment dgepay"),
    make_chunk(1, "ppt-004", "passport", "Documents to Carry", "documents for enrollment"),
    make_chunk(2, "nid-001", "nid", "NID Form 6", "form 6 lost nid card replacement"),
    make_chunk(3, "nid-003", "nid", "NID FAQ Correction", "correction faq name change"),
]


class FakeEmbedder:
    """Returns a chosen vector for a question, so tests need no network."""

    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors

    def embed_query(self, question: str) -> list[float]:
        return self.vectors.get(question, vec(0))


@pytest.fixture
def retriever(tmp_path):
    build_index(CHUNKS, [vec(0), vec(1), vec(2), vec(3)], index_dir=tmp_path / "chroma")
    keyword_index = build_keyword_index(CHUNKS, tmp_path / "bm25.json")
    embedder = FakeEmbedder(
        {"passport fee": vec(0), "lost nid card": vec(2), "documents needed": vec(1)}
    )
    return Retriever(open_collection(tmp_path / "chroma"), keyword_index, embedder, depth=2)


def test_doc_id_is_read_from_the_chunk_id():
    assert doc_id_of("nid-007-p003-c01") == "nid-007"
    assert doc_id_of("ppt-002-p000-c10") == "ppt-002"


def test_fusion_rewards_chunks_that_appear_in_both_lists():
    fused = reciprocal_rank_fusion({"meaning": ["a", "b"], "word": ["b", "c"]})
    assert [chunk_id for chunk_id, _ in fused] == ["b", "a", "c"]
    assert fused[0][1] == pytest.approx(1 / 62 + 1 / 61)


def test_fusion_weights_change_who_wins():
    rankings = {"meaning": ["a"], "word": ["b"]}
    assert reciprocal_rank_fusion(rankings, {"meaning": 2.0})[0][0] == "a"
    assert reciprocal_rank_fusion(rankings, {"word": 3.0})[0][0] == "b"


def test_fusion_ties_are_broken_the_same_way_every_time():
    fused = reciprocal_rank_fusion({"meaning": ["b", "a"], "word": ["a", "b"]})
    assert [chunk_id for chunk_id, _ in fused] == ["a", "b"]


def test_meaning_mode_ranks_by_similarity(retriever):
    results = retriever.retrieve("lost nid card", mode="meaning")
    assert results[0]["chunk_id"] == "nid-001-p000-c02"
    assert results[0]["meaning_score"] == pytest.approx(1.0, abs=1e-3)
    assert results[0]["word_score"] is None
    assert results[0]["url"] == "https://example.gov.bd/nid-001"


def test_word_mode_finds_by_words_and_fills_in_details(retriever):
    results = retriever.retrieve("lost nid card", mode="word")
    assert results[0]["chunk_id"] == "nid-001-p000-c02"
    assert results[0]["meaning_score"] is None
    assert results[0]["title"] == "NID Form 6"
    assert results[0]["text"] == "form 6 lost nid card replacement"


def test_hybrid_keeps_a_chunk_that_only_word_search_found(retriever):
    # Meaning search (depth 2) sees chunk 0 first. Only the words point to the enrollment chunk.
    results = retriever.retrieve("enrollment documents", mode="hybrid")
    ids = [result["chunk_id"] for result in results]
    assert "ppt-004-p000-c01" in ids
    found = next(result for result in results if result["chunk_id"] == "ppt-004-p000-c01")
    assert found["word_rank"] == 1
    assert found["title"] == "Documents to Carry"


def test_chunk_found_by_both_searches_ranks_first(retriever):
    results = retriever.retrieve("lost nid card", mode="hybrid")
    assert results[0]["chunk_id"] == "nid-001-p000-c02"
    assert results[0]["meaning_rank"] == 1
    assert results[0]["word_rank"] == 1


def test_service_filter_limits_both_searches(retriever):
    results = retriever.retrieve("lost nid card", mode="hybrid", service="passport")
    assert results
    assert all(result["service"] == "passport" for result in results)


def test_excluded_documents_never_appear(retriever):
    for mode in ("meaning", "word", "hybrid"):
        results = retriever.retrieve(
            "lost nid card", mode=mode, exclude_docs=frozenset({"nid-001"})
        )
        assert all(result["doc_id"] != "nid-001" for result in results)


def test_unknown_mode_is_an_error(retriever):
    with pytest.raises(ValueError, match="mode"):
        retriever.retrieve("anything", mode="magic")
