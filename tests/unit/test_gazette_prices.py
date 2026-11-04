"""Tests for removing Gazette page-price notes."""

from app.ingest.text_cleaning import strip_gazette_prices


def test_a_bangla_price_note_is_removed():
    text, count = strip_gazette_prices("আবেদন ২ (দুই) শত মূল্যঃ টাকা ২৪.০০\nপরের লাইন")
    assert (text, count) == ("আবেদন ২ (দুই) শত\nপরের লাইন", 1)


def test_an_ocr_price_note_with_latin_digits_is_removed():
    text, count = strip_gazette_prices("শত (৩০০৩) মূল্যঃ টাকা 8.00")
    assert (text, count) == ("শত (৩০০৩)", 1)


def test_the_colon_spelling_is_removed():
    assert strip_gazette_prices("মূল্য: টাকা ৮.০০") == ("", 1)


def test_several_notes_are_all_removed():
    text, count = strip_gazette_prices("এক মূল্যঃ টাকা ৮.০০\nদুই মূল্যঃ টাকা ২৪.০০")
    assert (text, count) == ("এক\nদুই", 2)


def test_fee_text_is_left_alone():
    text = "ফি ২০০ টাকা এবং মূল্য সংযোজন কর ১৫%"
    assert strip_gazette_prices(text) == (text, 0)
