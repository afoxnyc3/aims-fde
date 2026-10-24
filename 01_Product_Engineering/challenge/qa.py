"""Answer one question from the corpus, with sources, or decline.

The retriever is built on first use and kept: BM25 over ~116 pages is
instant, and the page embeddings are one batch of embedding calls per process.
"""

import os
from functools import lru_cache
from pathlib import Path

# LiteLLM raises subclasses of the OpenAI SDK's APIError for every provider,
# so one except clause covers timeouts, rate limits and auth failures.
from openai import APIError

import corpus
import retrieval
from qa_schema import QuestionAnswer, QuestionRequest, RetrievalTrace, ToolStep

# Chosen from use_case/evals/retrieval_results.md; the reasoning is the Week 3 row in decisions.md.
SHIPPED_TECHNIQUE = "agentic_hybrid"


class AnswerUnavailable(Exception):
    """The model or embedding service failed. Safe to show: carries no provider detail."""


@lru_cache(maxsize=1)
def get_retriever() -> retrieval.Retriever:
    # EMBED_CACHE_DIR, on a writable volume, saves re-embedding the corpus on every
    # restart. Unset (the default in the container), each process embeds once.
    cache_dir = os.getenv("EMBED_CACHE_DIR")
    return retrieval.Retriever(corpus.load_corpus(), cache_dir=Path(cache_dir) if cache_dir else None)


def answer_question(request: QuestionRequest) -> QuestionAnswer:
    retriever = get_retriever()
    try:
        result = retrieval.ask(request.question, SHIPPED_TECHNIQUE, retriever)
    except APIError as exc:
        raise AnswerUnavailable(f"the model service failed ({type(exc).__name__})") from None

    text = (result["answer"] or "").strip()
    sources = retrieval.cited_pages(text, retriever)
    dropped = sorted(set(retrieval.PAGE_ID.findall(text)) - set(sources))
    trace = RetrievalTrace(
        technique=SHIPPED_TECHNIQUE, model=retrieval.CHAT_MODEL,
        steps=[ToolStep(**step) for step in result["trace"]],
        evidence_chars=result["evidence_chars"], latency_s=result["latency_s"], stopped=result["stopped"],
    )

    # Retrieval always returns its top k, so "nothing matched" has to be decided
    # here. A similarity gate cannot do it on this corpus: the decline question's
    # best cosine sits inside the range of answerable ones (retrieval_results.md).
    # So the model declines explicitly, and code refuses to pass on any answer
    # that cites no real record. Only the model's one-line refusal is shown as a
    # reason; an uncited answer's text is never returned, since it is a guess.
    refusal = retrieval.decline_reason(text)
    if refusal:
        reason = refusal
        sources = []
    elif result["stopped"] == "max_turns":
        reason = "The turn budget ran out before the records answered the question."
    elif not sources:
        reason = "The answer cited no record in the corpus, so it was not passed on."
    else:
        reason = None

    if reason:
        return QuestionAnswer(question=request.question, declined=True, decline_reason=reason,
                              dropped_citations=dropped, trace=trace)
    return QuestionAnswer(question=request.question, declined=False, answer=text, sources=sources,
                          dropped_citations=dropped, trace=trace)
