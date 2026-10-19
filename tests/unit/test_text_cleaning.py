from app.ingest.text_cleaning import (
    fold_digits,
    normalize_text,
    redact_phones,
    scan_pii,
    split_pages,
    strip_header,
)


def test_fold_digits_converts_bangla_digits():
    assert fold_digits("১২৩ ৪৫০ abc 7") == "123 450 abc 7"


def test_normalize_removes_invisible_characters():
    assert normalize_text("a\u200bb\ufeffc\u00ad") == "abc"


def test_normalize_keeps_zwj_needed_for_bangla_spelling():
    assert "\u200d" in normalize_text("র\u200d্য")


def test_normalize_makes_equivalent_spellings_identical():
    assert normalize_text("\u09dc") == normalize_text("\u09a1\u09bc")


def test_normalize_tidies_whitespace():
    assert normalize_text("a  b\t\tc\n\n\n\nd  \n") == "a b c\n\nd"


def test_strip_header_removes_description_lines_but_keeps_body():
    raw = "# Title\nSource: x\nURL: y\nSection: z\n\nBody line"
    cleaned = strip_header(raw)
    assert "Source:" not in cleaned
    assert "URL:" not in cleaned
    assert "# Title" in cleaned
    assert "Body line" in cleaned


def test_split_pages_uses_markers():
    text = "--- Page 1 ---\nfirst\n--- Page 2 ---\nsecond"
    assert split_pages(text) == [(1, "first"), (2, "second")]


def test_split_pages_without_markers_gives_one_unnumbered_page():
    assert split_pages("just text") == [(None, "just text")]


def test_scan_pii_counts_phone_email_and_long_numbers():
    text = "call 01712345678 or ০১৭১২৩৪৫৬৭৮, mail a@b.gov.bd, id 1234567890123, year 2026 ১৪২১"
    counts = scan_pii(text)
    assert counts["phone"] == 2
    assert counts["email"] == 1
    assert counts["long_number"] == 1


def test_scan_pii_finds_phone_numbers_with_hyphens_and_country_code():
    text = "০১৭৩৩-৩৯৩৩০২ and +8801731541390 and 01733393302"
    assert scan_pii(text)["phone"] == 3


def test_scan_pii_ignores_landline_and_hotline_numbers():
    assert scan_pii("hotline ১০৫, phone +৮৮০২-৯১৩৪০১১")["phone"] == 0


def test_redact_phones_replaces_numbers_and_keeps_other_text():
    text = "ফোনঃ ০১৭৩৩-৩৯৩৩০২ ই-মেইল: a@b.gov.bd, 2026"
    cleaned, count = redact_phones(text)
    assert count == 1
    assert "০১৭৩৩" not in cleaned
    assert "[mobile number removed]" in cleaned
    assert "a@b.gov.bd" in cleaned
    assert "2026" in cleaned
