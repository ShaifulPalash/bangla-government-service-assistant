"""Tests for the number check."""

from app.graph.numbers import numbers_in, unsupported_numbers

PASSAGE = {
    "text": "Fee TK 4,025 for 48 pages",
    "title": "Fees",
    "page": None,
    "last_updated_date": "2026-07-12",
    "verified_date": "2026-10-14",
}


def test_numbers_are_normalised():
    assert numbers_in("TK ৪,০২৫ and BDT 172.50 [1]") == {"4025", "172.50"}


def test_citation_markers_are_not_numbers():
    assert numbers_in("See [12] and [১, ২]") == set()


def test_numbers_that_appear_in_the_sources_pass():
    answer = "TK ৪,০২৫ for 48 pages, updated 12 July 2026 [1]"
    assert unsupported_numbers(answer, [PASSAGE]) == []


def test_an_invented_number_is_reported():
    assert unsupported_numbers("The fee is TK 4,500", [PASSAGE]) == ["4500"]


def test_single_digit_numbers_are_ignored():
    assert unsupported_numbers("Step 1, then step 2", [PASSAGE]) == []
