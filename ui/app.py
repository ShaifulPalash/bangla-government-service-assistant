"""The Streamlit chat page for the Bangla Government-Service Assistant.

Run it locally with:  .venv-ui/bin/streamlit run ui/app.py
It only talks to the web API (see api_client.py); no search or AI code runs here.
"""

import os
import sys
from pathlib import Path

import streamlit as st

st.markdown(
    """
    <style>
    h1 {
        font-size: clamp(1.5rem, 3vw, 2rem) !important;
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Streamlit Community Cloud runs this file from the repository root, so we make the
# neighbouring api_client.py importable explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import (  # noqa: E402
    DEFAULT_API_URL,
    FEEDBACK_CATEGORIES,
    Answer,
    ApiClient,
    ApiError,
)
from bangla import (  # noqa: E402
    format_date,
    format_marks,
    format_page,
    is_bangla,
    localize_answer,
)

API_URL = os.environ.get("API_URL", DEFAULT_API_URL)
BANGLA = "বাংলা"
LANGUAGE_LABEL = "Interface language / ইন্টারফেসের ভাষা"

TEXT = {
    "en": {
        "title": "Bangla Government-Service Assistant",
        "subtitle": (
            "Answers about Bangladesh passport and NID services, taken from official "
            "documents and shown with their sources."
        ),
        "disclaimer": (
            "This is an independent informational project, not an official government "
            "service. It cannot submit applications or take payments. Please confirm "
            "important details on the official website."
        ),
        "privacy": (
            "Please do not type your NID, passport or phone number. Questions are "
            "processed by third-party AI services."
        ),
        "placeholder": "Ask about passports or NID...",
        "examples": "Try an example",
        "waking": "Waking up the server... the first visit can take up to a minute.",
        "server_failed": "The server did not respond. Please try again.",
        "retry": "Try again",
        "thinking": "Searching the official documents...",
        "sources": "Sources",
        "updated": "Updated",
        "checked": "Checked",
        "open": "Open the source page",
        "helpful": "Was this helpful?",
        "thanks": "Thank you for your feedback.",
        "what_wrong": "What was wrong?",
        "send": "Send",
        "cat_accuracy": "Incorrect information",
        "cat_incomplete": "Incomplete",
        "cat_outdated": "Outdated",
        "cat_unclear": "Unclear",
        "cat_other": "Other",
        "busy": "Too many questions right now. Please wait {seconds} seconds and try again.",
        "timeout": "The assistant took too long. Please try again.",
        "unavailable": (
            "The assistant is temporarily unavailable. Please try again in a few minutes."
        ),
        "invalid": "Please type a question of 2 to 300 characters.",
        "clear": "Clear the conversation",
        "debug": "Show technical details",
        "details": "Technical details",
        "about": (
            "Answers use the language of your question. The documents belong to the "
            "agencies that publish them; each answer links to its source."
        ),
    },
    "bn": {
        "title": "বাংলা সরকারি-সেবা সহকারী",
        "subtitle": ("বাংলাদেশের পাসপোর্ট ও এনআইডি সেবা সম্পর্কে সরকারি নথি থেকে উত্তর, সূত্রসহ।"),
        "disclaimer": (
            "এটি একটি স্বাধীন তথ্যভিত্তিক প্রকল্প, কোনো সরকারি সেবা নয়। এটি আবেদন জমা বা "
            "পেমেন্ট নিতে পারে না। গুরুত্বপূর্ণ তথ্য অফিসিয়াল ওয়েবসাইটে যাচাই করুন।"
        ),
        "privacy": (
            "অনুগ্রহ করে আপনার এনআইডি, পাসপোর্ট বা ফোন নম্বর লিখবেন না। প্রশ্ন তৃতীয় পক্ষের এআই সেবায় প্রক্রিয়া হয়।"
        ),
        "placeholder": "পাসপোর্ট বা এনআইডি সম্পর্কে প্রশ্ন করুন...",
        "examples": "একটি উদাহরণ চেষ্টা করুন",
        "waking": "সার্ভার চালু হচ্ছে... প্রথমবার এক মিনিট পর্যন্ত লাগতে পারে।",
        "server_failed": "সার্ভার সাড়া দেয়নি। আবার চেষ্টা করুন।",
        "retry": "আবার চেষ্টা করুন",
        "thinking": "সরকারি নথি খোঁজা হচ্ছে...",
        "sources": "সূত্র",
        "updated": "হালনাগাদ",
        "checked": "যাচাই করা হয়েছে",
        "open": "সূত্রের পাতা খুলুন",
        "helpful": "এটি কি সহায়ক ছিল?",
        "thanks": "আপনার মতামতের জন্য ধন্যবাদ।",
        "what_wrong": "কী সমস্যা ছিল?",
        "send": "পাঠান",
        "cat_accuracy": "ভুল তথ্য",
        "cat_incomplete": "অসম্পূর্ণ",
        "cat_outdated": "পুরনো তথ্য",
        "cat_unclear": "অস্পষ্ট",
        "cat_other": "অন্যান্য",
        "busy": "এখন অনেক প্রশ্ন আসছে। অনুগ্রহ করে {seconds} সেকেন্ড পর আবার চেষ্টা করুন।",
        "timeout": "সহকারী উত্তর দিতে দেরি করছে। আবার চেষ্টা করুন।",
        "unavailable": "সহকারী সাময়িকভাবে পাওয়া যাচ্ছে না। কয়েক মিনিট পরে আবার চেষ্টা করুন।",
        "invalid": "২ থেকে ৩০০ অক্ষরের মধ্যে একটি প্রশ্ন লিখুন।",
        "clear": "কথোপকথন মুছুন",
        "debug": "প্রযুক্তিগত তথ্য দেখান",
        "details": "প্রযুক্তিগত তথ্য",
        "about": (
            "উত্তর আপনার প্রশ্নের ভাষায় দেওয়া হয়। নথিগুলো প্রকাশকারী সংস্থার; প্রতিটি উত্তরে সূত্রের লিংক থাকে।"
        ),
    },
}

EXAMPLES = {
    "en": [
        "How much does an e-passport cost?",
        "What should I do if my NID card is lost?",
        "What documents do I need for e-passport enrollment?",
        "What is the fee for correcting an NID card?",
    ],
    "bn": [
        "ই-পাসপোর্টের ফি কত?",
        "এনআইডি কার্ড হারিয়ে গেলে কী করব?",
        "ই-পাসপোর্টের জন্য কী কী কাগজপত্র লাগে?",
        "এনআইডি কার্ডে তথ্য সংশোধনের ফি কত?",
    ],
}


TEXT["en"].update(
    {
        "notice_official": (
            "Independent informational project, not an official government service. "
            "It cannot submit applications or take payments. "
            "Confirm important details on the official website."
        ),
        "notice_privacy": (
            "Do not type your NID, passport or phone number. "
            "Questions are processed by third-party AI services."
        ),
        "repo": "Source code",
        "api_docs": "API documentation",
    }
)
TEXT["bn"].update(
    {
        "notice_official": (
            "এটি একটি স্বাধীন তথ্যভিত্তিক প্রকল্প, কোনো সরকারি সেবা নয়। "
            "এখান থেকে আবেদন বা পেমেন্ট করা যায় না। "
            "গুরুত্বপূর্ণ তথ্য অফিসিয়াল ওয়েবসাইটে যাচাই করুন।"
        ),
        "notice_privacy": (
            "এনআইডি, পাসপোর্ট বা ফোন নম্বর লিখবেন না। প্রশ্ন তৃতীয় পক্ষের এআই সেবায় প্রক্রিয়া হয়।"
        ),
        "repo": "সোর্স কোড",
        "api_docs": "এপিআই ডকুমেন্টেশন",
    }
)

REPO_URL = "https://github.com/ShaifulPalash/bangla-government-service-assistant"

STYLE = """
<style>
.block-container, [data-testid="stMainBlockContainer"] {
    max-width: 920px;
    padding-top: 3rem;
    padding-bottom: 5rem;
}
header[data-testid="stHeader"] { background: transparent; }
.app-banner {
    background: linear-gradient(135deg, #064e3b 0%, #0b6e4f 60%, #12805c 100%);
    border-bottom: 4px solid #f42a41;
    border-radius: 14px;
    margin-bottom: 0.8rem;
    padding: 1.1rem 1.4rem;
    text-align: center !important;
}
div.app-banner h1 {
    color: #ffffff !important;
    font-size: 1.55rem !important;
    font-weight: 700 !important;
    line-height: 1.25 !important;
    margin: 0 !important;
    padding: 0 !important;
    text-align: center !important;
}
div.app-banner p {
    color: rgba(255, 255, 255, 0.9) !important;
    font-size: 0.88rem !important;
    line-height: 1.5 !important;
    margin: 0.35rem auto 0 auto !important;
    max-width: 640px;
    text-align: center !important;
}
.app-banner.compact { padding: 0.55rem 1rem; border-bottom-width: 3px; }
div.app-banner.compact h1 { font-size: 1.1rem !important; }
div.app-banner.compact p { display: none !important; }
.notice {
    background: #f4f7f6;
    border-left: 3px solid #0b6e4f;
    border-radius: 6px;
    color: #3d4a46;
    font-size: 0.78rem;
    line-height: 1.45;
    margin-bottom: 0.45rem;
    padding: 0.45rem 0.8rem;
}
.notice.privacy { background: #fffaf0; border-left-color: #d97706; }
.section-label {
    color: #3d4a46;
    font-size: 0.82rem;
    font-weight: 600;
    margin: 0.8rem 0 0.3rem 0;
}
.st-key-examples button {
    border-radius: 10px;
    font-size: 0.86rem;
    text-align: left;
    width: 100%;
}
</style>
"""


def t(key: str, lang: str | None = None, **values) -> str:
    """Interface text in the sidebar language, or in `lang` when given."""
    text = TEXT[lang or st.session_state.lang][key]
    return text.format(**values) if values else text


def safe(text: str) -> str:
    """Streamlit treats $...$ as maths; escape the dollar sign so fees stay readable."""
    return text.replace("$", "\\$")


@st.cache_resource
def get_client(url: str) -> ApiClient:
    return ApiClient(url)


def ensure_server(client: ApiClient) -> bool:
    """Wake the free server once per visitor session."""
    if st.session_state.ready:
        return True
    with st.spinner(t("waking")):
        ready = client.wake_up()
    if ready:
        st.session_state.ready = True
        return True
    st.error(t("server_failed"))
    if st.button(t("retry")):
        st.rerun()
    return False


def show_sources(citations: list[dict], language: str) -> None:
    """One card per source document, in the same language as the answer."""
    if not citations:
        return
    lang = "bn" if is_bangla(language) else "en"
    st.markdown(f"**{t('sources', lang)}**")
    for citation in citations:
        numbers = citation.get("numbers")
        if not numbers:
            numbers = [citation["number"]] if citation.get("number") else []
        updated = citation.get("date_kind") == "updated"
        label = t("updated", lang) if updated else t("checked", lang)
        when = format_date(citation.get("date", ""), lang)
        page = f" · {format_page(citation['page'], lang)}" if citation.get("page") else ""
        with st.container(border=True):
            st.markdown(f"**{format_marks(numbers, lang)} {citation.get('title', '')}**")
            st.caption(f"{label}: {when}{page}")
            if citation.get("url"):
                st.link_button(t("open", lang), citation["url"])


def show_feedback(answer: Answer, client: ApiClient) -> None:
    """Thumbs up or down. A thumbs down asks what was wrong (the API's fixed categories)."""
    request_id = answer.request_id
    if not request_id or answer.decision == "unavailable":
        return
    state = st.session_state.feedback.get(request_id)
    if state == "sent":
        st.caption(t("thanks"))
    elif state == "open":
        category = st.selectbox(
            t("what_wrong"),
            FEEDBACK_CATEGORIES,
            format_func=lambda name: t(f"cat_{name}"),
            key=f"category-{request_id}",
        )
        if st.button(t("send"), key=f"send-{request_id}"):
            client.send_feedback(request_id, -1, category)  # best effort: never blocks
            st.session_state.feedback[request_id] = "sent"
            st.rerun()
    else:
        st.caption(t("helpful"))
        up, down, _ = st.columns([1, 1, 8])
        if up.button("👍", key=f"up-{request_id}"):
            client.send_feedback(request_id, 1)
            st.session_state.feedback[request_id] = "sent"
            st.rerun()
        if down.button("👎", key=f"down-{request_id}"):
            st.session_state.feedback[request_id] = "open"
            st.rerun()


def show_answer(answer: Answer, client: ApiClient, debug: bool) -> None:
    for notice in answer.notices:
        st.warning(notice)
    text = safe(localize_answer(answer.message, answer.language))
    if answer.decision == "answer":
        st.markdown(text)
    elif answer.decision == "clarify":
        st.info(text)
    elif answer.decision == "refuse":
        st.warning(text)
    else:
        st.error(text)
    show_sources(answer.citations, answer.language)
    if debug:
        with st.expander(t("details")):
            st.json(
                {
                    "decision": answer.decision,
                    "reason": answer.reason,
                    "provider": answer.provider,
                    "model": answer.model,
                    "cached": answer.cached,
                    "took_ms": answer.took_ms,
                    "path": answer.path,
                }
            )
    show_feedback(answer, client)


def error_text(error: ApiError) -> str:
    if error.kind == "busy":
        return t("busy", seconds=error.retry_after or 30)
    return t(error.kind)  # "timeout", "unavailable" or "invalid"


def ask_and_store(client: ApiClient, question: str) -> None:
    st.session_state.messages.append({"role": "user", "text": question})
    with st.chat_message("user"):
        st.markdown(safe(question))
    try:
        with st.spinner(t("thinking")):
            answer = client.ask(question)
    except ApiError as error:
        st.session_state.messages.append({"role": "assistant", "error": error_text(error)})
    else:
        st.session_state.messages.append({"role": "assistant", "answer": answer})
    st.rerun()  # redraw the whole conversation, including the feedback buttons


def show_sidebar() -> bool:
    """Interface language, technical-details switch, and links. Returns the debug flag."""
    choice = st.sidebar.radio(LANGUAGE_LABEL, ["English", BANGLA], key="ui_language")
    st.session_state.lang = "bn" if choice == BANGLA else "en"
    debug = st.sidebar.checkbox(t("debug"))
    if st.sidebar.button(t("clear")):
        st.session_state.messages = []
        st.session_state.feedback = {}
        st.rerun()
    st.sidebar.caption(t("about"))
    st.sidebar.markdown(f"[{t('repo')}]({REPO_URL})  \n[{t('api_docs')}]({API_URL}/docs)")
    return debug


def show_header(compact: bool) -> None:
    """The banner. It shrinks to one line once the conversation has started."""
    css_class = "app-banner compact" if compact else "app-banner"
    st.markdown(
        f'<div class="{css_class}"><h1>🏛️ {t("title")}</h1><p>{t("subtitle")}</p></div>',
        unsafe_allow_html=True,
    )


def show_notices() -> None:
    """The disclaimer and the privacy warning, small and clearly secondary."""
    st.markdown(
        f'<div class="notice">ℹ️ {t("notice_official")}</div>'
        f'<div class="notice privacy">🔒 {t("notice_privacy")}</div>',
        unsafe_allow_html=True,
    )


def show_examples() -> None:
    """Example questions in a two-column grid, so they take little height."""
    st.markdown(f'<div class="section-label">{t("examples")}</div>', unsafe_allow_html=True)
    with st.container(key="examples"):
        columns = st.columns(2)
        for index, example in enumerate(EXAMPLES[st.session_state.lang]):
            if columns[index % 2].button(example, key=f"example-{index}"):
                st.session_state.queued = example
                st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Bangla Government-Service Assistant",
        page_icon="🏛️",
        layout="wide",
    )
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("feedback", {})
    st.session_state.setdefault("ready", False)

    debug = show_sidebar()
    st.markdown(STYLE, unsafe_allow_html=True)
    show_header(compact=bool(st.session_state.messages))
    show_notices()

    client = get_client(API_URL)
    if not ensure_server(client):
        st.stop()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(safe(message["text"]))
            elif "error" in message:
                st.error(message["error"])
            else:
                show_answer(message["answer"], client, debug)

    if not st.session_state.messages:
        show_examples()

    question = st.chat_input(t("placeholder"), max_chars=300) or st.session_state.pop(
        "queued", None
    )
    if question:
        ask_and_store(client, question)


main()
