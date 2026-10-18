from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ingest import pdf_extractor
from app.ingest.pdf_extractor import (
    OCR_LANGUAGES,
    extract_pdf_pages,
    format_pages,
    looks_like_usable_text,
)


def test_bengali_text_is_usable():
    text = "বাংলাদেশ নির্বাচন কমিশন " * 10

    assert looks_like_usable_text(text)


def test_english_text_is_usable():
    text = "Bangladesh Election Commission official information " * 5

    assert looks_like_usable_text(text, "en")


def test_mixed_language_text_is_usable():
    text = "বাংলাদেশ Election Commission নির্বাচন কমিশন " * 5

    assert looks_like_usable_text(text, "mixed")


def test_empty_text_is_not_usable():
    assert not looks_like_usable_text("")


def test_short_text_is_not_usable():
    assert not looks_like_usable_text("বাংলা")


def test_unsupported_language_is_rejected():
    with pytest.raises(ValueError, match="Unsupported language"):
        looks_like_usable_text("Some text", "fr")


def test_language_models_match_registry_labels():
    assert OCR_LANGUAGES == {
        "bn": "ben",
        "en": "eng",
        "mixed": "ben+eng",
    }


def test_page_boundaries_are_preserved():
    result = format_pages(["প্রথম পৃষ্ঠা", "দ্বিতীয় পৃষ্ঠা"])

    assert "--- Page 1 ---" in result
    assert "--- Page 2 ---" in result
    assert "প্রথম পৃষ্ঠা" in result
    assert "দ্বিতীয় পৃষ্ঠা" in result


def test_only_unusable_pages_are_sent_to_ocr(tmp_path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.touch()

    readable_page = "বাংলাদেশ নির্বাচন কমিশন " * 10
    reader = SimpleNamespace(
        is_encrypted=False,
        pages=[
            SimpleNamespace(extract_text=lambda: readable_page),
            SimpleNamespace(extract_text=lambda: ""),
        ],
    )
    monkeypatch.setattr(pdf_extractor, "PdfReader", lambda _: reader)

    calls = {}

    def fake_ocr(path: Path, page_numbers: list[int], language: str = "bn"):
        calls["path"] = path
        calls["page_numbers"] = page_numbers
        calls["language"] = language
        return {2: "OCR থেকে পাওয়া লেখা"}

    monkeypatch.setattr(pdf_extractor, "_extract_with_ocr", fake_ocr)

    result = extract_pdf_pages(pdf_path, language="bn")

    assert result == [readable_page, "OCR থেকে পাওয়া লেখা"]
    assert calls == {
        "path": pdf_path,
        "page_numbers": [2],
        "language": "bn",
    }


def test_usable_embedded_text_does_not_call_ocr(tmp_path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.touch()

    readable_page = "Bangladesh Election Commission official information " * 5
    reader = SimpleNamespace(
        is_encrypted=False,
        pages=[SimpleNamespace(extract_text=lambda: readable_page)],
    )
    monkeypatch.setattr(pdf_extractor, "PdfReader", lambda _: reader)

    def fail_if_called(*args, **kwargs):
        pytest.fail("OCR should not run for usable embedded text")

    monkeypatch.setattr(pdf_extractor, "_extract_with_ocr", fail_if_called)

    assert extract_pdf_pages(pdf_path, language="en") == [readable_page]


def test_encrypted_pdf_is_rejected(tmp_path, monkeypatch):
    pdf_path = tmp_path / "encrypted.pdf"
    pdf_path.touch()

    reader = SimpleNamespace(is_encrypted=True, pages=[])
    monkeypatch.setattr(pdf_extractor, "PdfReader", lambda _: reader)

    with pytest.raises(ValueError, match="encrypted"):
        extract_pdf_pages(pdf_path)
