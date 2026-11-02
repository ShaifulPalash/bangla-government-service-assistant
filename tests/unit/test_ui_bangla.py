"""Tests for the Bangla display helpers."""

import pytest
from ui.bangla import (
    bangla_digits,
    format_date,
    format_marks,
    format_page,
    is_bangla,
    localize_answer,
)


def test_taka_amounts_and_digits_become_bangla():
    assert localize_answer("Regular TK 4,025, express TK 6,325.", "bn") == (
        "Regular ৪,০২৫ টাকা, express ৬,৩২৫ টাকা."
    )


def test_bdt_with_decimals():
    assert localize_answer("BDT 172.50 (15% VAT)", "bn") == "১৭২.৫০ টাকা (১৫% VAT)"


def test_citation_marks_and_dates_in_the_text_become_bangla():
    assert localize_answer("Updated 2026-07-12 [1][2]", "bn") == "Updated ২০২৬-০৭-১২ [১][২]"


def test_list_numbers_become_bangla_and_keep_their_own_lines():
    result = localize_answer("1. first\n2. second", "bn")
    assert result == "১. first  \n২. second"


def test_banglish_questions_also_get_bangla_digits():
    assert localize_answer("TK 500", "bn-latn") == "৫০০ টাকা"


def test_english_answers_are_left_alone():
    text = "TK 4,025 on 2026-07-12\n1. first"
    assert localize_answer(text, "en") == text


def test_the_digit_mapping_keeps_the_value():
    english = "0123456789"
    assert bangla_digits(english) == "০১২৩৪৫৬৭৮৯"
    # converting back gives the original digits, so no figure can change
    assert bangla_digits("4,025").translate(str.maketrans("০১২৩৪৫৬৭৮৯", english)) == "4,025"


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "12 July 2026"), ("bn", "১২ জুলাই ২০২৬"), ("bn-latn", "১২ জুলাই ২০২৬")],
)
def test_dates(language, expected):
    assert format_date("2026-07-12", language) == expected


def test_an_unreadable_date_is_returned_as_it_is():
    assert format_date("soon", "en") == "soon"
    assert format_date("১২", "bn") == "১২"


def test_marks_and_pages():
    assert format_marks([1, 2], "en") == "[1], [2]"
    assert format_marks([1, 2], "bn") == "[১], [২]"
    assert format_page(3, "en") == "p. 3"
    assert format_page(3, "bn") == "পৃ. ৩"


def test_language_check():
    assert is_bangla("bn") and is_bangla("bn-latn") and not is_bangla("en")
