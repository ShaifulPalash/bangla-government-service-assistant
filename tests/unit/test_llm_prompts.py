from app.llm.prompts import (
    MAX_PASSAGE_CHARS,
    SYSTEM_PROMPT,
    ParsedAnswer,
    build_user_prompt,
    format_sources,
    parse_answer,
)


def passage(**overrides) -> dict:
    data = {
        "title": "E-Passport Fees",
        "text": "Regular delivery: TK 4,025",
        "last_updated_date": "2026-07-12",
        "verified_date": "2026-10-14",
        "page": None,
    }
    data.update(overrides)
    return data


def test_sources_are_numbered_and_show_their_title_and_date():
    text = format_sources([passage(), passage(title="Other", last_updated_date="", page=3)])
    assert text.startswith("[1] E-Passport Fees (updated 2026-07-12)\nRegular delivery")
    assert "[2] Other (checked 2026-10-14, page 3)" in text


def test_long_passages_are_trimmed_and_whitespace_is_collapsed():
    text = format_sources([passage(text="word   " * 500)])
    body = text.split("\n", 1)[1]
    assert len(body) == MAX_PASSAGE_CHARS
    assert "  " not in body


def test_user_prompt_contains_the_sources_and_the_question():
    prompt = build_user_prompt("What is the fee?", [passage()])
    assert prompt.startswith("SOURCES\n[1]")
    assert prompt.endswith("QUESTION\nWhat is the fee?")


def test_system_prompt_states_the_key_rules():
    for phrase in ("ONLY", "can_answer", "data, not instructions", "individual officer"):
        assert phrase in SYSTEM_PROMPT


def test_plain_json_is_read():
    parsed = parse_answer('{"can_answer": true, "answer": "TK 4,025 [1]", "sources": [1]}')
    assert parsed == ParsedAnswer(True, "TK 4,025 [1]", [1])


def test_json_in_code_fences_or_with_extra_words_is_read():
    fenced = '```json\n{"can_answer": false, "answer": "Not found.", "sources": []}\n```'
    assert parse_answer(fenced) == ParsedAnswer(False, "Not found.", [])
    chatty = 'Sure! {"can_answer": true, "answer": "Yes [2]", "sources": [2]} Hope it helps.'
    assert parse_answer(chatty).sources == [2]


def test_source_numbers_given_as_text_are_accepted_and_junk_is_dropped():
    parsed = parse_answer('{"can_answer": true, "answer": "x", "sources": ["1", 2, "abc"]}')
    assert parsed.sources == [1, 2]


def test_unreadable_reply_is_kept_as_text_with_unknown_can_answer():
    parsed = parse_answer("The fee is TK 4,025.")
    assert parsed.can_answer is None
    assert parsed.answer == "The fee is TK 4,025."
    assert parse_answer('{"can_answer": "maybe", "answer": "x"}').can_answer is None


def test_user_prompt_names_the_answer_language_when_given():
    prompt = build_user_prompt("What is the fee?", [passage()], "English")
    assert prompt.endswith("QUESTION\nWhat is the fee?\n\nANSWER LANGUAGE\nEnglish")


def test_system_prompt_requires_exact_numbers_and_plain_citations():
    assert "exactly as they are written" in SYSTEM_PROMPT
    assert "plain square brackets" in SYSTEM_PROMPT
    assert "ANSWER LANGUAGE" in SYSTEM_PROMPT
