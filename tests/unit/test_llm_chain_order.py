"""The chain must try Groq first and Gemini second, using only the keys that exist."""

from app.config import Settings
from app.llm.providers import build_chain


def providers(**keys) -> list[str]:
    # _env_file=None stops the test from reading your real .env file
    settings = Settings(_env_file=None, **keys)
    return [client.provider for client in build_chain(settings).clients]


def test_groq_is_first_and_gemini_is_the_backup():
    assert providers(groq_api_key="g", gemini_api_key="m") == ["groq", "gemini"]


def test_only_the_configured_keys_are_used():
    assert providers(gemini_api_key="m") == ["gemini"]
    assert providers(groq_api_key="g") == ["groq"]
