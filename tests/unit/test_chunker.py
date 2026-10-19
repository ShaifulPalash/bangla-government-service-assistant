from app.indexing.chunker import MAX_CHARS, build_chunks, split_text


def make_document(pages):
    return {
        "id": "nid-007",
        "title": "Rules",
        "url": "https://example.gov.bd/rules",
        "service": "nid",
        "language": "bn",
        "publisher": "EC",
        "last_updated_date": None,
        "verified_date": "2026-10-15",
        "extraction": "ocr_reviewed",
        "pages": pages,
    }


def test_short_text_is_one_chunk():
    assert split_text("A short passage about passports.") == ["A short passage about passports."]


def test_long_text_is_cut_into_chunks_within_the_limit():
    text = " ".join(f"Sentence number {i} about the passport fee." for i in range(200))
    chunks = split_text(text)
    assert len(chunks) > 1
    assert all(0 < len(chunk) <= MAX_CHARS for chunk in chunks)


def test_paragraph_breaks_are_preferred():
    first = ("First paragraph. " * 30).strip()
    second = ("Second paragraph. " * 30).strip()
    chunks = split_text(first + "\n\n" + second)
    assert chunks[0] == first
    assert chunks[1].endswith(second)


def test_neighbouring_chunks_overlap():
    text = " ".join(f"word{i}" for i in range(400))
    chunks = split_text(text, max_chars=300, overlap=60)
    assert len(chunks) > 2
    assert chunks[0].split()[-1] in chunks[1].split()


def test_bangla_sentences_are_cut_at_the_danda():
    sentence = "পাসপোর্টের আবেদন অনলাইনে জমা দিতে হবে। "
    chunks = split_text(sentence * 40, max_chars=300, overlap=0)
    assert len(chunks) > 1
    assert all(chunk.endswith("।") for chunk in chunks)


def test_text_without_separators_is_hard_split():
    chunks = split_text("x" * 1000, max_chars=300, overlap=0)
    assert all(len(chunk) <= 300 for chunk in chunks)
    assert "".join(chunks) == "x" * 1000


def test_build_chunks_keeps_pages_apart_and_carries_metadata():
    document = make_document(
        [
            {"page": 1, "text": "Page one text that is long enough to keep."},
            {"page": 2, "text": "Page two text that is long enough to keep."},
        ]
    )
    chunks = build_chunks(document)
    assert [chunk["chunk_id"] for chunk in chunks] == ["nid-007-p001-c00", "nid-007-p002-c00"]
    assert chunks[1]["page"] == 2
    assert chunks[0]["title"] == "Rules"
    assert chunks[0]["text"] == "Page one text that is long enough to keep."


def test_unpaged_document_uses_page_none():
    document = make_document([{"page": None, "text": "x" * 50}])
    chunks = build_chunks(document)
    assert chunks[0]["page"] is None
    assert chunks[0]["chunk_id"] == "nid-007-p000-c00"
