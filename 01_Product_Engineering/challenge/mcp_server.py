"""Way 2 (TC5): the onboarding question capability as an MCP server.

Two tools, chosen with MCP_TOOLSET (comma-separated; unknown values stop the server):
- `answer` (the shipped default): `answer_onboarding_question`, the guarded question endpoint.
  It wraps qa.answer_question, so declines, citation checks and the no-credentials rule run
  here, and the caller gets the answer and its sources, never raw records. It is a subagent
  behind MCP: a model loop that reads a lot and returns a little.
- `search`: `search_hybrid`, the same raw search Way 1 gives its model, with the same
  description. Used only for the like-for-like TC5 measurement.

Run it:      uv run python mcp_server.py                (stdio)
             MCP_PRELOAD=1 loads and embeds the corpus before serving, so the
             first question does not pay for it.

Middleware, in order: AuditCounter (counts calls that reach the capability; logs every
call's shape, never its content, plus the model tokens and turns the server spent on it) and
ToolErrorMessages (unknown tools and bad arguments as short messages that never echo
input; an upstream outage as the fixed UPSTREAM_UNAVAILABLE marker).
"""

import contextvars
import json
import os
import time
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import NotFoundError, ToolError
from fastmcp.exceptions import ValidationError as ArgumentsInvalid
from fastmcp.server.middleware import Middleware
from typing import Annotated

from pydantic import Field, ValidationError

from openai import APIError

import litellm

import llm
import qa
import retrieval
from qa_schema import QuestionRequest

# Model tokens the server spends on behalf of a call (the guarded tool runs its own
# retrieval loop). Counted here because the outside client cannot see them. One counter
# per call, in a ContextVar: FastMCP runs sync tools in worker threads (anyio copies the
# context in), so two overlapping calls each count only their own completions.
_call_tokens: contextvars.ContextVar[dict | None] = contextvars.ContextVar("call_tokens", default=None)
_raw_call_with_retry = llm.call_with_retry


def _counting_call_with_retry(call, **kwargs):
    response = _raw_call_with_retry(call, **kwargs)
    counter = _call_tokens.get()
    if counter is not None and call is litellm.completion:
        counter["total"] += int(getattr(response.usage, "total_tokens", 0) or 0)
        counter["turns"] += 1
    return response


def install_token_counter() -> None:
    """Count the server's own model tokens. Called only when this module runs as the
    server, so importing it (tests, the measurement client) changes nothing globally."""
    llm.call_with_retry = _counting_call_with_retry


# Which tools the server exposes. Shipped default: the guarded endpoint only. The TC5
# measurement sets MCP_TOOLSET=search to compare raw search like for like with Way 1.
KNOWN_TOOLSETS = {"answer", "search"}
TOOLSET = {part.strip() for part in (os.getenv("MCP_TOOLSET") or "answer").split(",") if part.strip()}

# Every parameter name a tool here takes. The audit log records only these, plus a count of
# any others: a client chooses its argument names, so an unknown key can carry content.
KNOWN_ARG_KEYS = {"question", "query", "k"}

# The capability lives in retrieval.py, unchanged. Loading the corpus is lazy so
# the server starts (and lists its tools) even before the corpus is mounted.
_retriever = None

# Fixed marker for an upstream API outage. Clients must treat it as a failed run, not as evidence.
UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE: the retrieval service could not reach its model API."


def _get():
    global _retriever
    if _retriever is None:
        _retriever = qa.get_retriever()
    return _retriever


def _root_error(exc: BaseException) -> str:
    """Class name of the original failure, under FastMCP's and our ToolError wrappers."""
    seen = exc
    while isinstance(seen, ToolError) and (seen.__cause__ or seen.__context__):
        seen = seen.__cause__ or seen.__context__
    return type(seen).__name__


# Calls rejected before the capability ran: they are logged but are not capability calls.
REJECTED_BEFORE_CAPABILITY = {"NotFoundError", "ValidationError"}


class AuditCounter(Middleware):
    """Counts the calls that reach the capability, and logs every call's shape (never its content).

    `calls` matches Way 1's counter: how many times the function actually ran. Unknown
    tools and malformed arguments are rejected before it runs, so they are logged with
    reached=false and not counted.
    """

    def __init__(self, log_path: str | None = None):
        self.calls: dict[str, int] = {}
        self.log_path = Path(log_path) if log_path else None

    async def on_call_tool(self, context, call_next):
        name = context.message.name
        started = time.perf_counter()
        tokens = {"total": 0, "turns": 0}
        token = _call_tokens.set(tokens)
        result, error = None, None
        try:
            result = await call_next(context)
            return result
        except Exception as exc:
            error = _root_error(exc)
            raise
        finally:
            _call_tokens.reset(token)
            # A call that reached the capability counts whether it succeeded or raised;
            # a call rejected by dispatch or validation is logged but not counted.
            reached = error not in REJECTED_BEFORE_CAPABILITY
            if reached:
                self.calls[name] = self.calls.get(name, 0) + 1
            if self.log_path:
                size = sum(len((getattr(block, "text", "") or "").encode("utf-8"))
                           for block in getattr(result, "content", []) or [])
                keys = (context.message.arguments or {}).keys()
                line = {"tool": name, "arg_keys": sorted(k for k in keys if k in KNOWN_ARG_KEYS),
                        "unknown_arg_count": sum(1 for k in keys if k not in KNOWN_ARG_KEYS),
                        "response_bytes": size, "ms": round((time.perf_counter() - started) * 1000),
                        "error": error, "reached": reached,
                        "server_model_tokens": tokens["total"], "server_model_turns": tokens["turns"]}
                with self.log_path.open("a") as handle:
                    handle.write(json.dumps(line) + "\n")


class ToolErrorMessages(Middleware):
    """A failed call is a message the model can act on, never a traceback or an echo of its input.

    Unknown tool: names the tools that do exist, so the model can recover in one turn.
    Bad arguments: field and problem only. Pydantic's default text echoes the input
    back, and arguments can carry ticket text.
    """

    async def on_call_tool(self, context, call_next):
        name = context.message.name
        try:
            return await call_next(context)
        except NotFoundError:
            tools = ", ".join(sorted(t.name for t in await context.fastmcp_context.fastmcp.list_tools()))
            raise ToolError(f"Unknown tool '{name}'. Available tools: {tools}.") from None
        except ArgumentsInvalid as exc:
            cause = exc.__cause__
            if isinstance(cause, ValidationError):
                problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
                                     for e in cause.errors(include_input=False))
            else:
                problems = "arguments do not match the tool's schema"
            raise ToolError(f"Bad arguments for '{name}': {problems}.") from None
        except ToolError as exc:
            # FastMCP wraps the capability's exception in a masked ToolError before this
            # middleware sees it; the original is on __cause__. An embedding/model API
            # outage gets a fixed marker so the CLIENT can abort the run, as Way 1 does
            # (run_agent re-raises APIError rather than let the model decline politely).
            if isinstance(exc.__cause__, (APIError, qa.AnswerUnavailable)):
                raise ToolError(UPSTREAM_UNAVAILABLE) from None
            raise


def build_server(audit: AuditCounter | None = None, toolset: set[str] | None = None) -> FastMCP:
    toolset = toolset or TOOLSET
    unknown = set(toolset) - KNOWN_TOOLSETS
    if unknown or not toolset:
        raise ValueError(f"MCP_TOOLSET must be one or more of {sorted(KNOWN_TOOLSETS)}; got {sorted(toolset)}")
    audit = audit or AuditCounter(os.getenv("MCP_AUDIT_LOG"))
    server = FastMCP("onboarding-qa", middleware=[audit, ToolErrorMessages()], mask_error_details=True)

    if "answer" in toolset:
        @server.tool
        def answer_onboarding_question(
                question: Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S",
                                               description="The question in plain language.")]) -> str:
            """Answer a question about onboarding tickets and the draft access standard.
            Returns JSON: the answer, the records it cites (sources), and, if the
            service declined, why. Never returns raw records or credentials."""
            answer = qa.answer_question(QuestionRequest(question=question))
            return answer.model_dump_json(exclude={"trace"})

    if "search" in toolset:
        # Same name, description and parameter wording as Way 1's hand-written schema
        # (retrieval.TECHNIQUES["agentic_hybrid"]). Not byte-identical: FastMCP adds "default": 4 on k
        # and "additionalProperties": false. test_mcp_server pins exactly that difference.
        way1 = retrieval.TECHNIQUES["agentic_hybrid"][0]["function"]

        @server.tool(description=way1["description"])
        def search_hybrid(query: str,
                          k: Annotated[int, Field(description="results, 1-8")] = 4) -> str:
            return _get().search_hybrid(query, k)

    return server


if __name__ == "__main__":
    # The measurement sets HIT_CHARS to compare demo-size and real-size responses. Applied only
    # when this runs as the server, so importing it (measure_tc5.py, tests) leaves retrieval alone.
    if os.getenv("HIT_CHARS"):
        retrieval.HIT_CHARS = int(os.environ["HIT_CHARS"])
    install_token_counter()
    server = build_server()
    if os.getenv("MCP_PRELOAD"):
        _get().search_hybrid("warm-up", 1)  # loads the corpus and its embeddings; no chat model call
    server.run()
