"""The server.

`gradio.Server` is a FastAPI app with Gradio's API engine bolted in. You get
queueing, streaming, and MCP for free, but you bring your own frontend. That
split is the point: the API is the product, the UI is disposable.
"""

import os
from pathlib import Path

from fastapi.responses import HTMLResponse
from gradio import Error, Server
from pydantic import ValidationError

from corpus import CorpusMissing
from llm import ReplyError, stream_reply
from qa import AnswerUnavailable, answer_question
from qa_schema import QuestionRequest
from schema import Request, solve

app = Server()

FRONTEND = Path(__file__).parent / "frontend" / "index.html"


# --- The API -----------------------------------------------------------------


def _validation_details(exc: ValidationError) -> str:
    """Field paths and messages only: the rejected input is never echoed back."""
    return "; ".join(
        ".".join(str(part) for part in error["loc"]) + ": " + error["msg"]
        for error in exc.errors(include_input=False)
    )


# The `-> str` return annotation is REQUIRED. Without it Gradio infers zero
# output components and silently returns nothing. Ask us how we know.


@app.api(name="chat")
def chat(message: str, history: list | None = None) -> str:
    """Stream a reply to one user message."""
    try:
        yield from stream_reply(message, history)
    except ReplyError as exc:
        raise Error(str(exc)) from None


@app.api(name="recommend_onboarding_access")
def recommend_onboarding_access(onboarding_ticket_json: str) -> str:
    """Recommend standard access for one masked synthetic onboarding ticket.

    Send Request JSON with ticket_ref, ticket_text, and comments. Comments carry
    trusted JSM author IDs/types and timestamps; optional redacted_sections and
    unavailable_sections mark gaps. Return Response JSON: a recommendation,
    clarification/review, ignored ticket, or processing failure. No account or
    ticket writes. Invalid input is a validation error, not a failed Response.
    """
    try:
        request = Request.model_validate_json(onboarding_ticket_json)
    except ValidationError as exc:
        raise Error("Invalid onboarding request: " + _validation_details(exc)) from None
    return solve(request).model_dump_json()


@app.api(name="answer_onboarding_question")
def answer_onboarding_question(question_json: str) -> str:
    """Answer a question about onboarding tickets or the draft access standard, citing records.

    Send JSON {"question": "..."}: one plain-language question, up to 2000
    characters. For example: which clubs give a Lifeguard a staff login; what
    standard role a ticket's job title maps to; what happened on a named new
    hire's ticket; how a kind of ticket is routed.

    Returns QuestionAnswer JSON. When answered, `answer` names its records in
    square brackets and `sources` lists them: SYN-* pages are synthetic
    onboarding tickets, STD-* pages are the draft v0.1 standard (unratified).
    When the records do not support an answer, `declined` is true, `answer` is
    null and `decline_reason` says why; do not answer from elsewhere. `trace`
    lists every retrieval call. Read-only: no tickets or accounts are changed,
    and it never returns credentials. Invalid JSON is a validation error.
    """
    try:
        request = QuestionRequest.model_validate_json(question_json)
    except ValidationError as exc:
        raise Error("Invalid question: " + _validation_details(exc)) from None
    try:
        return answer_question(request).model_dump_json()
    except CorpusMissing:
        raise Error("The retrieval corpus is not mounted; set CORPUS_PATH.") from None
    except AnswerUnavailable as exc:
        raise Error(f"No answer: {exc}. Try again later.") from None


# --- The frontend ------------------------------------------------------------
# Defining a route at "/" replaces Gradio's default UI with ours.


@app.get("/", response_class=HTMLResponse)
def homepage() -> str:
    return FRONTEND.read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    """Your future ops team will thank you. Load balancers need this."""
    return {"status": "ok", "model": os.getenv("LLM_MODEL", "gpt-4.1-mini")}


if __name__ == "__main__":
    # 0.0.0.0 so the container is reachable from the host. On your laptop this
    # is fine. On a firm network, "reachable from where, exactly?" is the
    # question this challenge wants you to go ask.
    #
    # Read the port rather than hardcoding it, so a machine that already has
    # something on 7860 can move this one without editing code.
    port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))

    # Gradio announces the address it BOUND to, which is 0.0.0.0 -- not an
    # address a browser can open. Windows rejects it outright; macOS and Linux
    # quietly redirect it to localhost, which is why it looks fine on some
    # machines and broken on others. Print the one that always works.
    print(f"\n  Open http://localhost:{port} in your browser\n", flush=True)
    app.launch(server_name="0.0.0.0", server_port=port)
