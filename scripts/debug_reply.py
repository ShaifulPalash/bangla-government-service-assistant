"""Show the raw reply of each language model for one question (debugging only)."""

from __future__ import annotations

import sys

from app.config import get_settings
from app.graph.routing import classify_service
from app.indexing.embeddings import PROJECT_ROOT
from app.llm.language import answer_language, detect_language
from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt, parse_answer
from app.llm.providers import LLMError, build_chain
from app.retrieval.hybrid import build_retriever

QUERY_CACHE = PROJECT_ROOT / "data" / "processed" / "query_cache.jsonl"


def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else "পাসপোর্ট ফি কত?"
    settings = get_settings()
    retriever = build_retriever(settings.gemini_api_key.get_secret_value(), QUERY_CACHE)
    service = classify_service(question)
    service = service if service in ("passport", "nid") else None
    passages = retriever.retrieve(question, k=3, service=service)
    prompt = build_user_prompt(question, passages, answer_language(detect_language(question)))
    print(f"prompt length: {len(prompt)} characters, {len(passages)} passages")

    for client in build_chain(settings).clients:
        print("=" * 70)
        try:
            reply = client.generate(SYSTEM_PROMPT, prompt)
        except LLMError as error:
            print(f"{client.provider}/{client.model} FAILED: {error}")
            continue
        parsed = parse_answer(reply.text)
        print(
            f"{client.provider}/{client.model} | output_tokens={reply.output_tokens} "
            f"| can_answer={parsed.can_answer}"
        )
        print("length:", len(reply.text), "characters")
        print("START:", reply.text[:200])
        print("END  :", reply.text[-200:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
