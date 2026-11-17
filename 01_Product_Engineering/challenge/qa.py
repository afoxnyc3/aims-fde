"""Answer one question from the corpus, with sources, or decline.

The retriever is built on first use and kept: BM25 over ~116 pages is
instant, and the page embeddings are one batch of embedding calls per process.
"""

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

# LiteLLM raises subclasses of the OpenAI SDK's APIError for every provider,
# so one except clause covers timeouts, rate limits and auth failures.
from openai import APIError

import corpus
import inputrail
import outcheck
import retrieval
from qa_schema import QuestionAnswer, QuestionRequest, RetrievalTrace, ToolStep

# Chosen from use_case/evals/retrieval_results.md; the reasoning is the Week 3 row in decisions.md.
SHIPPED_TECHNIQUE = "agentic_hybrid"

# The full trace, tool arguments included, is for operators. Callers get tool name and size only.
TRACE_LOG = logging.getLogger("qa.trace")
# The tool name in a step is the model's too: it can call a tool that does not exist and name it
# anything. Only our own tool names are passed on; any other becomes this fixed string.
KNOWN_TOOLS = frozenset(tool["function"]["name"] for tools in retrieval.TECHNIQUES.values() for tool in tools)
UNKNOWN_TOOL = "unknown_tool"
# The gates TC6 added. All are always on for callers: no setting, environment variable or request
# field turns one off (plan decision D7). `skip_gates` on answer_question exists so tests and the
# measurement scripts can price a gate by running the same questions without it.
#   input_rail    the NeMo input rail in guardrails/, before the model
#   run_citation  a cited page must have been returned by a tool call in this run (T1-20)
#   output_check  approval, link and marker rules on the model's text (T1-21)
TC6_GATES = frozenset({"input_rail", "run_citation", "output_check"})


class AnswerUnavailable(Exception):
    """The model or embedding service failed. Safe to show: carries no provider detail."""


@lru_cache(maxsize=1)
def get_retriever() -> retrieval.Retriever:
    # EMBED_CACHE_DIR, on a writable volume, saves re-embedding the corpus on every
    # restart. Unset (the default in the container), each process embeds once.
    cache_dir = os.getenv("EMBED_CACHE_DIR")
    return retrieval.Retriever(corpus.load_corpus(), cache_dir=Path(cache_dir) if cache_dir else None)


def source_page(name: str) -> corpus.Page | None:
    """One corpus page by name, so a reader can check a source an answer cited.

    The corpus is loaded first, so a missing corpus is reported whatever name
    was sent. Only full page names match (SYN-xxxxxx or STD-...).
    """
    retriever = get_retriever()
    page = retriever.get_page(name)
    return page if page and retrieval.PAGE_ID.fullmatch(page.name) else None


def answer_question(request: QuestionRequest, *, skip_gates: frozenset[str] = frozenset()) -> QuestionAnswer:
    """Answer or decline. `skip_gates` is for tests and measurement scripts only; see TC6_GATES."""
    if not skip_gates <= TC6_GATES:
        raise ValueError(f"unknown gate: {sorted(skip_gates - TC6_GATES)}")
    # Input rail first: a question a rung stops never reaches the model or the retriever's tools.
    # The reason is fixed text; the trace says which stage stopped it and that no call was made.
    if "input_rail" not in skip_gates and inputrail.stopped_by(request.question):
        return QuestionAnswer(
            question=request.question, declined=True, decline_reason=inputrail.DECLINE,
            trace=RetrievalTrace(technique=SHIPPED_TECHNIQUE, model=retrieval.CHAT_MODEL, steps=[],
                                 evidence_chars=0, latency_s=0.0, stopped="input_rail"))
    retriever = get_retriever()
    try:
        result = retrieval.ask(request.question, SHIPPED_TECHNIQUE, retriever)
    except APIError as exc:
        raise AnswerUnavailable(f"the model service failed ({type(exc).__name__})") from None

    text = (result["answer"] or "").strip()
    # Only pages a tool call returned in this run count as sources. A result without the list
    # counts as nothing returned, so the gate fails closed.
    returned = None if "run_citation" in skip_gates else result.get("returned_pages") or []
    sources = retrieval.cited_pages(text, retriever, returned)
    # A decline reason is model text shown to the user too, so its ids are reported the same way:
    # invented ones, and real ones no call in this run returned.
    said = text or result.get("decline_reason") or ""
    dropped = sorted(set(retrieval.PAGE_ID.findall(said)) - set(retrieval.cited_pages(said, retriever, returned)))
    trace = RetrievalTrace(
        technique=SHIPPED_TECHNIQUE, model=retrieval.CHAT_MODEL,
        # Tool name and character count only: the arguments are model text and stay server-side.
        steps=[ToolStep(tool=step["tool"] if step["tool"] in KNOWN_TOOLS else UNKNOWN_TOOL, chars=step["chars"])
               for step in result["trace"]],
        evidence_chars=result["evidence_chars"], latency_s=result["latency_s"], stopped=result["stopped"],
        retried=result.get("retried", False),
    )

    TRACE_LOG.info("%s", json.dumps({"question": request.question, "stopped": result["stopped"],
                                     "steps": result["trace"]}, ensure_ascii=False, default=str))

    # Retrieval always returns its top k, so "nothing matched" has to be decided
    # here. A similarity gate cannot do it on this corpus: the decline question's
    # best cosine sits inside the range of answerable ones (retrieval_results.md).
    # So the model must end in an answer or a decline tool call, and code refuses to
    # pass on any answer that cites no real record. The flag comes from which call it
    # made, never from the reply's wording. Only the decline's one-line reason is shown;
    # an uncited answer's text is never returned, since it is a guess.
    if result["stopped"] == "declined":
        reason = result["decline_reason"]
        sources = []
    elif result["stopped"] == "unstructured":
        reason = "The model replied without choosing to answer or decline, so the reply was not passed on."
        sources = []
    elif result["stopped"] == "max_turns":
        reason = "The turn budget ran out before the records answered the question."
    elif not sources:
        reason = "The answer cited no record that this run's searches returned, so it was not passed on."
    else:
        reason = None

    # Output check: model text shown to the user, answer or decline reason, may not state an
    # approval the cited tickets' status fields do not carry, nor give a link from outside the
    # standard. The fixed reason replaces the text; none of it is passed on.
    # The same goes for the prompt's own marker: a decline reason is the model's words, and one
    # run in eight put the marker in it ("Internal marker ... must not be revealed").
    marker = getattr(retrieval, "PROMPT_MARKER", None)
    blocked = None if "output_check" in skip_gates else outcheck.withheld_reason(
        text if not reason else reason, sources, retriever.pages, marker)
    if blocked:
        reason = blocked
    # An invented page name is model text too: [SYN-7f3a91] is well-formed and is the marker's tail.
    dropped = [name for name in dropped if not outcheck.carries_marker(name, marker)]

    if reason:
        return QuestionAnswer(question=request.question, declined=True, decline_reason=reason,
                              dropped_citations=dropped, trace=trace)
    return QuestionAnswer(question=request.question, declined=False, answer=text, sources=sources,
                          dropped_citations=dropped, trace=trace)
