from app.ingest.documents import FINAL_TEXT, KEEP_FIELDS, build_record
from app.ingest.sources import load_registry


def make_meta(source_id="nid-007"):
    meta = {key: "x" for key in KEEP_FIELDS}
    meta["id"] = source_id
    return meta


def test_build_record_cleans_text_and_splits_pages(tmp_path):
    file = tmp_path / "doc.txt"
    file.write_text(
        "Source: somewhere\nURL: https://x\n\n"
        "--- Page 1 ---\nfirst\u200b page, call 01712345678\n"
        "--- Page 2 ---\nsecond page\n",
        encoding="utf-8",
    )
    record = build_record(make_meta("ppt-006"), file, "ocr_reviewed")
    assert [page["page"] for page in record["pages"]] == [1, 2]
    assert record["pages"][0]["text"] == "first page, call [mobile number removed]"
    assert "Source:" not in record["pages"][0]["text"]
    assert record["extraction"] == "ocr_reviewed"
    assert record["phones_removed"] == 1
    assert record["pii_flags"]["phone"] == 0
    assert record["replacement_chars"] == 0


def test_build_record_counts_replacement_characters(tmp_path):
    file = tmp_path / "doc.txt"
    file.write_text("bad \ufffd text \ufffd here", encoding="utf-8")
    record = build_record(make_meta(), file, "web_text")
    assert record["replacement_chars"] == 2
    assert record["pages"][0]["page"] is None


def test_every_source_has_a_final_text_file():
    source_ids = {source.id for source in load_registry().sources}
    assert source_ids == set(FINAL_TEXT)


def test_phones_are_kept_but_flagged_for_other_sources(tmp_path):
    file = tmp_path / "doc.txt"
    file.write_text("helpline 01712345678", encoding="utf-8")
    record = build_record(make_meta("nid-002"), file, "web_text")
    assert record["phones_removed"] == 0
    assert record["pii_flags"]["phone"] == 1
    assert "01712345678" in record["pages"][0]["text"]
