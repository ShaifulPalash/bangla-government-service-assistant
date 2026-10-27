"""List the language models your API keys can use.

Run:  PYTHONPATH=src python scripts/list_llm_models.py

It prints model names and limits only. It never prints your keys.
"""

import httpx

from app.config import get_settings

# Gemini also lists image, audio and embedding models. We only want text chat models.
SKIP_WORDS = ("image", "tts", "audio", "live", "embedding", "imagen", "veo", "robotics")


def error_text(response: httpx.Response) -> str:
    """The error message from the provider, if it sent one."""
    try:
        return str(response.json().get("error", {}).get("message", response.text[:200]))
    except ValueError:
        return response.text[:200]


def list_gemini(api_key: str) -> None:
    try:
        response = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"pageSize": 200},
            headers={"x-goog-api-key": api_key},
            timeout=30,
        )
    except httpx.HTTPError as error:
        print(f"Gemini: could not connect ({type(error).__name__})")
        return
    print(f"Gemini: HTTP {response.status_code}")
    if response.status_code != 200:
        print(f"  error: {error_text(response)}")
        return
    for model in response.json().get("models", []):
        name = model["name"]
        can_chat = "generateContent" in model.get("supportedGenerationMethods", [])
        if can_chat and not any(word in name for word in SKIP_WORDS):
            limits = (
                f"input {model.get('inputTokenLimit')} | output {model.get('outputTokenLimit')}"
            )
            print(f"  {name} | {limits}")


def list_groq(api_key: str) -> None:
    try:
        response = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except httpx.HTTPError as error:
        print(f"Groq: could not connect ({type(error).__name__})")
        return
    print(f"Groq: HTTP {response.status_code}")
    if response.status_code != 200:
        print(f"  error: {error_text(response)}")
        return
    for model in response.json().get("data", []):
        print(f"  {model['id']} | context {model.get('context_window')}")


def main() -> int:
    settings = get_settings()
    if settings.gemini_api_key:
        list_gemini(settings.gemini_api_key.get_secret_value())
    else:
        print("Gemini: there is no GEMINI_API_KEY in .env")
    if settings.groq_api_key:
        list_groq(settings.groq_api_key.get_secret_value())
    else:
        print("Groq: there is no GROQ_API_KEY in .env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
