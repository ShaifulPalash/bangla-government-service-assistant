import json

import pytest

from app.indexing.keyword_index import build_keyword_index, load_keyword_index
from app.indexing.vector_index import IndexMismatchError


def make_chunk(i: int, text: str, title: str = "Page", service: str = "nid") -> dict:
    return {"chunk_id": f"doc-p000-c0{i}", "title": title, "service": service, "text": text}


def sample_chunks() -> list[dict]:
    return [
        make_chunk(
            0, "The e-passport fee depends on validity and delivery time.", service="passport"
        ),
        make_chunk(1, "জাতীয় পরিচয়পত্র সংশোধনের জন্য ফরম ২ পূরণ করতে হবে। ফি ১২০০ টাকা।"),
        make_chunk(2, "Documents to carry for enrollment.", title="NID Correction Rules"),
    ]


def test_finds_the_chunk_that_contains_the_query_words(tmp_path):
    index = build_keyword_index(sample_chunks(), tmp_path / "bm25.json")
    assert index.search("passport fee")[0]["chunk_id"] == "doc-p000-c00"


def test_bangla_digits_in_text_match_ascii_digits_in_the_question(tmp_path):
    index = build_keyword_index(sample_chunks(), tmp_path / "bm25.json")
    assert index.search("1200 টাকা")[0]["chunk_id"] == "doc-p000-c01"


def test_words_in_the_document_title_are_searchable(tmp_path):
    index = build_keyword_index(sample_chunks(), tmp_path / "bm25.json")
    assert index.search("correction")[0]["chunk_id"] == "doc-p000-c02"


def test_search_can_be_limited_to_one_service(tmp_path):
    index = build_keyword_index(sample_chunks(), tmp_path / "bm25.json")
    assert [hit["chunk_id"] for hit in index.search("fee", service="passport")] == ["doc-p000-c00"]
    assert index.search("ফি", service="passport") == []


def test_no_shared_word_gives_no_results(tmp_path):
    index = build_keyword_index(sample_chunks(), tmp_path / "bm25.json")
    assert index.search("zzzz") == []


def test_a_question_with_no_words_gives_no_results(tmp_path):
    index = build_keyword_index(sample_chunks(), tmp_path / "bm25.json")
    assert index.search("।!?") == []


def test_saved_index_loads_and_searches_the_same(tmp_path):
    path = tmp_path / "bm25.json"
    build_keyword_index(sample_chunks(), path)
    loaded = load_keyword_index(path)
    assert loaded.search("passport fee")[0]["chunk_id"] == "doc-p000-c00"


def test_a_changed_tokenizer_is_detected(tmp_path):
    path = tmp_path / "bm25.json"
    build_keyword_index(sample_chunks(), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tokenizer_check"] = ["something", "else"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(IndexMismatchError, match="Rebuild"):
        load_keyword_index(path)


def test_missing_index_file_gives_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="make build-keyword-index"):
        load_keyword_index(tmp_path / "nothing.json")


def test_building_with_no_chunks_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no chunks"):
        build_keyword_index([], tmp_path / "bm25.json")
