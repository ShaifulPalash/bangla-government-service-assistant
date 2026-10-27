"""The question-answering workflow, built with LangGraph.

Every question travels through small steps (nodes) and ends in ONE of four outcomes:
  answer       an answer with citations
  clarify      a question back to the user ("passport or NID?")
  refuse       a fixed or model-written "I can't help with that"
  unavailable  a service problem (search or language model down)

    prepare -> classify -> retrieve -> evidence -> answer -> respond
        |          |           |           |           |
     refuse     refuse     unavailable  clarify /    unavailable /
     (safety)   (scope)                 refuse       refuse (model)

The cheap steps run first, so many questions never reach the language model.
Note: no "from __future__ import annotations" here, because LangGraph reads the State
annotations at run time.
"""

import logging
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.graph.evidence import best_score, has_enough_evidence
from app.graph.routing import classify_service, is_out_of_scope_topic
from app.graph.safety import message_for, safety_check
from app.indexing.embeddings import EmbeddingError
from app.llm.language import answer_language, detect_language
from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt, parse_answer
from app.llm.providers import LLMError

logger = logging.getLogger(__name__)

TOP_K = 3  # passages sent to the model: few passages keep the prompt (and the cost) small

# Fixed replies. They cost no tokens and always say the same thing.
MESSAGES = {
    "clarify": {
        "en": "Which service is your question about: passport or NID? "
        "Please add a few more details.",
        "bn": "আপনার প্রশ্নটি কোন সেবা সম্পর্কে: পাসপোর্ট নাকি এনআইডি? অনুগ্রহ করে একটু বিস্তারিত লিখুন।",
    },
    "out_of_scope": {
        "en": "I can only help with Bangladesh passport and NID services. For other services, "
        "please use the official website of the agency that provides them.",
        "bn": "আমি শুধু বাংলাদেশের পাসপোর্ট ও এনআইডি সেবা নিয়ে সাহায্য করতে পারি। "
        "অন্য সেবার জন্য সংশ্লিষ্ট সংস্থার অফিসিয়াল ওয়েবসাইট দেখুন।",
    },
    "no_evidence": {
        "en": "I could not find this in the official documents I have. Please check the "
        "official websites (epassport.gov.bd for passports, nidw.gov.bd for NID) "
        "or contact the relevant office.",
        "bn": "আমার কাছে থাকা সরকারি নথিতে আমি এটি খুঁজে পাইনি। অনুগ্রহ করে অফিসিয়াল ওয়েবসাইট "
        "(পাসপোর্টের জন্য epassport.gov.bd, এনআইডির জন্য nidw.gov.bd) দেখুন "
        "অথবা সংশ্লিষ্ট অফিসে যোগাযোগ করুন।",
    },
    "unavailable": {
        "en": "The assistant is temporarily unavailable. Please try again in a few minutes.",
        "bn": "সহকারী সাময়িকভাবে পাওয়া যাচ্ছে না। কয়েক মিনিট পরে আবার চেষ্টা করুন।",
    },
}


def say(key: str, language: str) -> str:
    """A fixed reply in English ('en') or Bangla (every other language code)."""
    return MESSAGES[key]["en" if language == "en" else "bn"]


class State(TypedDict, total=False):
    """The notebook that every node reads from and writes to."""

    question: str  # input; "prepare" replaces it with the version without personal numbers
    redacted: list[str]  # kinds of personal numbers removed, e.g. ["NID_NUMBER"]
    blocked_reason: str | None  # set when the safety check refuses the question
    language: str  # "bn", "bn-latn" or "en"
    service: str  # "passport", "nid", "both" or "unclear"
    out_of_scope: bool
    passages: list[dict]  # what the search found
    retrieval_failed: bool
    top_score: float
    enough_evidence: bool
    llm: dict  # the language model's parsed reply
    llm_failed: bool
    result: dict  # the final outcome, built by the last node
    path: Annotated[list[str], operator.add]  # node names visited; "add" joins the lists


def finish(
    state: State, decision: str, reason: str, message: str, citations: list | None = None
) -> dict:
    """Build the final result. Every ending of the graph goes through here."""
    language = state.get("language", "en")
    llm = state.get("llm") or {}
    result = {
        "decision": decision,
        "reason": reason,
        "message": message,
        "language": language,
        "service": state.get("service"),
        "citations": citations or [],
        "notices": [message_for("privacy", language)] if state.get("redacted") else [],
        "top_score": state.get("top_score"),
        "provider": llm.get("provider"),
        "model": llm.get("model"),
    }
    return {"result": result}


def build_graph(retriever, chain, top_k: int = TOP_K):
    """Connect the nodes. `retriever` and `chain` are passed in so tests can use fakes."""

    # ---- nodes: each does one job and returns only what it changes ------------------------
    def prepare(state: State) -> dict:
        checked = safety_check(state["question"])  # removes personal numbers, spots attacks
        return {
            "question": checked.question,
            "redacted": checked.redacted,
            "blocked_reason": checked.blocked_reason,
            "language": detect_language(checked.question),
            "path": ["prepare"],
        }

    def classify(state: State) -> dict:
        service = classify_service(state["question"])
        out_of_scope = service == "unclear" and is_out_of_scope_topic(state["question"])
        return {"service": service, "out_of_scope": out_of_scope, "path": ["classify"]}

    def retrieve(state: State) -> dict:
        service = state["service"] if state["service"] in ("passport", "nid") else None
        try:
            passages = retriever.retrieve(state["question"], k=top_k, service=service)
        except EmbeddingError as error:
            logger.error("retrieval failed: %s", error)
            return {"retrieval_failed": True, "passages": [], "path": ["retrieve"]}
        return {
            "retrieval_failed": False,
            "passages": passages,
            "top_score": best_score(passages),
            "path": ["retrieve"],
        }

    def evidence(state: State) -> dict:
        return {"enough_evidence": has_enough_evidence(state["passages"]), "path": ["evidence"]}

    def answer(state: State) -> dict:
        language_name = answer_language(state["language"])
        prompt = build_user_prompt(state["question"], state["passages"], language_name)
        try:
            reply = chain.generate(SYSTEM_PROMPT, prompt)
        except LLMError as error:
            logger.error("all language models failed: %s", error)
            return {"llm_failed": True, "path": ["answer"]}
        parsed = parse_answer(reply.text)
        llm = {
            "can_answer": parsed.can_answer,
            "answer": parsed.answer,
            "sources": parsed.sources,
            "provider": reply.provider,
            "model": reply.model,
        }
        return {"llm": llm, "llm_failed": False, "path": ["answer"]}

    # ---- routers: look at the state and name the next node ---------------------------------
    def after_prepare(state: State) -> str:
        return "refuse_safety" if state.get("blocked_reason") else "classify"

    def after_classify(state: State) -> str:
        return "refuse_scope" if state["out_of_scope"] else "retrieve"

    def after_retrieve(state: State) -> str:
        return "unavailable" if state["retrieval_failed"] else "evidence"

    def after_evidence(state: State) -> str:
        if state["enough_evidence"]:
            return "answer"
        # Weak evidence: if we do not even know the service, ask; otherwise say we found nothing.
        return "clarify" if state["service"] == "unclear" else "refuse_no_evidence"

    def after_answer(state: State) -> str:
        if state["llm_failed"] or state["llm"]["can_answer"] is None:
            return "unavailable"  # the model was down, or its reply could not be read
        return "respond" if state["llm"]["can_answer"] else "refuse_model"

    # ---- ending nodes: each builds the final result --------------------------------------
    def refuse_safety(state: State) -> dict:
        reason = state["blocked_reason"]
        message = message_for(reason, state["language"])
        return {"path": ["refuse_safety"], **finish(state, "refuse", reason, message)}

    def refuse_scope(state: State) -> dict:
        message = say("out_of_scope", state["language"])
        return {"path": ["refuse_scope"], **finish(state, "refuse", "out_of_scope", message)}

    def clarify(state: State) -> dict:
        message = say("clarify", state["language"])
        return {"path": ["clarify"], **finish(state, "clarify", "service_unclear", message)}

    def refuse_no_evidence(state: State) -> dict:
        message = say("no_evidence", state["language"])
        return {"path": ["refuse_no_evidence"], **finish(state, "refuse", "no_evidence", message)}

    def refuse_model(state: State) -> dict:
        # The model itself said it could not answer; its short reply is in the right language.
        message = state["llm"]["answer"]
        return {"path": ["refuse_model"], **finish(state, "refuse", "model_declined", message)}

    def unavailable(state: State) -> dict:
        if state.get("retrieval_failed"):
            reason = "retrieval_unavailable"
        elif state.get("llm_failed"):
            reason = "llm_unavailable"
        else:
            reason = "unreadable_reply"
        message = say("unavailable", state["language"])
        return {"path": ["unavailable"], **finish(state, "unavailable", reason, message)}

    def respond(state: State) -> dict:
        """Show the answer, but only with citations that point at real passages."""
        passages, llm = state["passages"], state["llm"]
        citations = []
        for number in dict.fromkeys(llm["sources"]):  # unique numbers, in order
            if 1 <= number <= len(passages):
                p = passages[number - 1]
                citations.append(
                    {
                        "number": number,
                        "title": p["title"],
                        "url": p["url"],
                        "doc_id": p["doc_id"],
                        "page": p["page"],
                        "date": p["last_updated_date"] or p["verified_date"],
                        "date_kind": "updated" if p["last_updated_date"] else "checked",
                    }
                )
        if not citations:  # an answer nobody can check is not shown
            message = say("no_evidence", state["language"])
            return {
                "path": ["respond"],
                **finish(state, "refuse", "no_valid_citation", message),
            }
        return {
            "path": ["respond"],
            **finish(state, "answer", "ok", llm["answer"], citations),
        }

    # ---- wiring ----------------------------------------------------------------------------
    graph = StateGraph(State)
    nodes = {
        "prepare": prepare,
        "classify": classify,
        "retrieve": retrieve,
        "evidence": evidence,
        "answer": answer,
        "respond": respond,
        "refuse_safety": refuse_safety,
        "refuse_scope": refuse_scope,
        "clarify": clarify,
        "refuse_no_evidence": refuse_no_evidence,
        "refuse_model": refuse_model,
        "unavailable": unavailable,
    }
    for name, function in nodes.items():
        graph.add_node(name, function)

    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", after_prepare, ["refuse_safety", "classify"])
    graph.add_conditional_edges("classify", after_classify, ["refuse_scope", "retrieve"])
    graph.add_conditional_edges("retrieve", after_retrieve, ["unavailable", "evidence"])
    graph.add_conditional_edges(
        "evidence", after_evidence, ["answer", "clarify", "refuse_no_evidence"]
    )
    graph.add_conditional_edges("answer", after_answer, ["unavailable", "respond", "refuse_model"])
    for ending in (
        "respond",
        "refuse_safety",
        "refuse_scope",
        "clarify",
        "refuse_no_evidence",
        "refuse_model",
        "unavailable",
    ):
        graph.add_edge(ending, END)
    return graph.compile()


def ask(graph, question: str) -> dict:
    """Run one question through the graph. Returns the result plus the path it took."""
    final = graph.invoke({"question": question, "path": []})
    result = {**final["result"], "path": final["path"]}
    # The question text is not logged: it could still contain personal details.
    logger.info(
        "question_len=%d decision=%s reason=%s language=%s service=%s top=%s path=%s",
        len(question),
        result["decision"],
        result["reason"],
        result["language"],
        result["service"],
        result["top_score"],
        ">".join(result["path"]),
    )
    return result
