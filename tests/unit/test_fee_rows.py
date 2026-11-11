"""Tests for labelling fee rows with their applicant group."""

from app.ingest.text_cleaning import label_fee_rows

SAMPLE = """e-Passport fees for inside Bangladesh (Including 15% VAT)

e-Passport with 48 pages and 5 years validity
Regular delivery: TK 4,025
Express delivery: TK 6,325

e-Passport fees for Bangladesh Mission's General Applicants:

e-Passport with 48 pages and 5 years validity
Regular delivery : USD 100
"""


def test_every_fee_row_gets_its_group_and_type():
    text, count = label_fee_rows(SAMPLE)
    assert count == 3
    assert (
        "Fee for inside Bangladesh (Including 15% VAT) | 48 pages, 5 years validity | "
        "Regular delivery: TK 4,025"
    ) in text
    assert (
        "Fee for Bangladesh Mission's General Applicants | 48 pages, 5 years validity | "
        "Regular delivery : USD 100"
    ) in text


def test_the_original_row_text_is_kept_inside_the_new_line():
    text, _ = label_fee_rows(SAMPLE)
    assert "Express delivery: TK 6,325" in text


def test_text_without_fee_tables_is_unchanged():
    plain = "Apply online.\nPay the fee at a bank."
    assert label_fee_rows(plain) == (plain, 0)


def test_a_row_without_a_passport_type_is_not_labelled():
    text = "e-Passport fees for inside Bangladesh\nRegular delivery: TK 1"
    assert label_fee_rows(text) == (text, 0)


def test_a_non_breaking_hyphen_in_the_heading_still_works():
    text = (
        "e\u2011Passport fees for inside Bangladesh\n"
        "e\u2011Passport with 64 pages and 10 years validity\n"
        "Express delivery: TK 10,350"
    )
    result, count = label_fee_rows(text)
    assert count == 1
    assert (
        "Fee for inside Bangladesh | 64 pages, 10 years validity | Express delivery: TK 10,350"
    ) in result


def test_non_breaking_spaces_do_not_break_the_match():
    text = (
        "e-Passport\u00a0fees\u00a0for inside Bangladesh\n"
        "e-Passport with 48 pages and 5 years\u00a0validity\n"
        "Regular\u00a0delivery\u00a0: TK 1,000"
    )
    result, count = label_fee_rows(text)
    assert count == 1
