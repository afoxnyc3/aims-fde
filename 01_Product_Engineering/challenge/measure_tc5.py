"""TC5 Steps 4 and 5: measure Way 1 (tool in the app) against Way 2 (MCP server).

Same model, same system prompt, same capability (`search_hybrid`), same two
requests. Four numbers per run: model calls, capability calls, seconds, tokens.
Plus the first turn's parallel tool-call count and the bytes per response.

    uv run --env-file ../../.env python measure_tc5.py                 # demo + real size
    uv run --env-file ../../.env python measure_tc5.py --size real

Way 2 keeps one warm server session per size, as Claude Desktop does; its start-up
(handshake and first search) is recorded separately as mcp_session_start.

Way 1's capability calls are counted in process. Way 2's are counted twice:
on the client (what the loop asked for) and on the server (what actually ran,
read back from the server's audit log), because the client cannot see inside
the server process. That second count is the process-boundary finding.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import litellm
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

import llm
import mcp_server
import qa
import retrieval

HERE = Path(__file__).parent

REQUESTS = {
    "one lookup": "Hospitality Associate Level 1: what role do I use?",
    "several lookups": ("Three new hires start Monday at the same club: a Hospitality Associate Level 1, "
                        "a Lifeguard and a Personal Trainer Level 2. For each one, which role do I use, "
                        "and does the standard give them a company mailbox?"),
}
# Demo scale cuts each hit to a snippet; real scale is what the endpoint returns (whole records).
SIZES = {"demo": 300, "real": retrieval.HIT_CHARS}


FINAL_NAMES = {retrieval.ANSWER_TOOL, retrieval.DECLINE_TOOL}


class Meter:
    """Model round trips, tokens, and how many tool calls the first turn asked for."""

    def __init__(self):
        self.calls = 0
        self.tokens = 0
        self.first_turn_tool_calls = None

    def wrap(self, call_with_retry):
        def counted(call, **kwargs):
            response = call_with_retry(call, **kwargs)
            if call is litellm.completion:
                self.calls += 1
                self.tokens += int(getattr(response.usage, "total_tokens", 0) or 0)
                if self.first_turn_tool_calls is None:  # capability calls only, not answer/decline
                    calls = response.choices[0].message.tool_calls or []
                    self.first_turn_tool_calls = sum(call.function.name not in FINAL_NAMES for call in calls)
            return response
        return counted


class CountingRetriever:
    """Way 1's capability counter: the function runs here, so we can count it here."""

    def __init__(self, inner):
        self.inner, self.calls, self.response_bytes = inner, 0, []

    def search_hybrid(self, query, k=4):
        out = self.inner.search_hybrid(query, k)
        self.calls += 1
        self.response_bytes.append(len(out.encode()))
        return out

    def __getattr__(self, name):
        return getattr(self.inner, name)


def way1_tool(question: str, meter: Meter, retriever) -> dict:
    counting = CountingRetriever(retriever)
    retrieval.llm.call_with_retry = meter.wrap(llm_call)
    result = retrieval.run_agent(question, "agentic_hybrid", counting)
    return {"capability": counting.calls, "server_count": None, "bytes": counting.response_bytes,
            "answer": result.get("answer", ""), "declined": result["stopped"] != "answer"}


async def way2_mcp(question: str, meter: Meter, client: Client, audit: Path, system: str = retrieval.SYSTEM,
                   final_tools: bool = True) -> dict:
    """Same loop as retrieval.run_agent, but tools are discovered from and dispatched to the server.

    With `final_tools` (Way 2), the model also gets run_agent's answer and decline tools and must end
    in one, so its declines are read the same way. Without (2b, an outside client such as Claude
    Desktop), it gets the server's tools only and answers in prose; its declines come from the
    server's structured `declined` field.

    The server session is opened once per size and kept warm, as Claude Desktop keeps a stdio
    server alive for a session. Its start-up cost is measured separately (see open_session).
    """
    audit.write_text("")
    client_calls, answer, declined, server_declined = 0, "", False, 0
    listed = await client.list_tools()
    tools = [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                                               "parameters": getattr(t, "input_schema", None) or t.inputSchema}} for t in listed]
    extra = {"tool_choice": "required"} if final_tools else {}
    if final_tools:
        tools += retrieval.FINAL_TOOLS
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    call = meter.wrap(llm_call)
    for _ in range(retrieval.MAX_TURNS):
        response = call(litellm.completion, model=retrieval.CHAT_MODEL, messages=messages, tools=tools,
                        timeout=120, num_retries=0, **extra, **retrieval.CHAT_KWARGS)
        message = response.choices[0].message
        if final_tools:
            step = retrieval.final_step(message)
            if step:
                answer = step[1] if step[0] == "answer" else ""
                declined = step[0] != "answer"
                break
        elif not message.tool_calls:
            answer = message.content or ""
            break
        messages.append(message.model_dump(exclude_none=True))
        for tool_call in message.tool_calls:
            client_calls += 1
            # Arguments the model got wrong are a message it can recover from, as in Way 1's run_agent
            # (which also rejects JSON that is not an object). A failure on the client-server transport
            # is infrastructure, not the model's doing, so it propagates and fails the run, like an outage.
            try:
                args = json.loads(tool_call.function.arguments or "{}")
                if not isinstance(args, dict):
                    raise TypeError("arguments must be a JSON object")
            except (ValueError, TypeError) as exc:
                messages.append({"role": "tool", "tool_call_id": tool_call.id,
                                 "content": f"(tool error: {type(exc).__name__})"})
                continue
            result = await client.call_tool(tool_call.function.name, args, raise_on_error=False)
            output = "".join(getattr(b, "text", "") for b in result.content) or "(empty result)"
            if result.is_error:
                if mcp_server.UPSTREAM_UNAVAILABLE in output:
                    # Same contract as Way 1: an outage fails the run, it is never evidence.
                    raise RuntimeError("upstream API outage during an MCP tool call")
                output = f"(tool error: {output[:200]})"
            else:
                server_declined += _declined(output)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": output})
    lines = [json.loads(line) for line in audit.read_text().splitlines() if line.strip()]
    reached = [line for line in lines if line.get("reached", True)]
    return {"capability": client_calls, "server_count": len(reached),
            "server_failed": sum(1 for line in reached if line.get("error")),
            "server_ms": sum(line["ms"] for line in reached),
            "server_tokens": sum(line.get("server_model_tokens", 0) for line in reached),
            "server_turns": sum(line.get("server_model_turns", 0) for line in reached),
            "bytes": [line["response_bytes"] for line in reached], "answer": answer,
            "declined": declined, "server_declined": server_declined}


def _declined(output: str) -> bool:
    """The guarded tool's own verdict: its JSON says declined. Raw search returns text, never this."""
    try:
        body = json.loads(output)
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("declined") is True


# Way 2b: the guarded tool as an outside client in the organisation's Claude workspace (Desktop and similar clients) would use it. The
# client model gets a short generic prompt; retrieval, declines and citation checks run
# inside the server, whose own model tokens are counted from the audit log.
CLIENT_SYSTEM = ("You are a helpful assistant for the IT service desk. Use the onboarding tool to answer "
                 "questions about onboarding tickets and the access standard. Report what it returns, "
                 "including its sources; do not add facts it did not give you.")


async def open_session(hit_chars: int, audit: Path, toolset: str = "search"):
    """Start the MCP server warm; return the client and the timings.

    MCP_PRELOAD makes the server load and embed the corpus before it answers the
    handshake, so that cost lands in handshake_s, not in the first measured question."""
    env = {**os.environ, "MCP_AUDIT_LOG": str(audit), "HIT_CHARS": str(hit_chars), "MCP_TOOLSET": toolset,
           "MCP_PRELOAD": "1"}
    transport = PythonStdioTransport(str(HERE / "mcp_server.py"), env=env, cwd=str(HERE), keep_alive=True)
    client = Client(transport)
    started = time.perf_counter()
    await client.__aenter__()
    handshake = time.perf_counter() - started
    await client.list_tools()
    return client, {"handshake_s": round(handshake, 2), "first_call_s": round(time.perf_counter() - started - handshake, 2)}


def graded(answer: str, label: str, server_declined: int = 0, declined: bool = False) -> dict:
    """answered: there is final text, the loop did not decline, and the server declined no call.

    `declined` is structural: Way 1 and Way 2 end in an answer or decline call. 2b's outside client
    answers in prose, so its only structured signal is the server's `declined` field; a prose refusal
    from that client with no server decline counts as answered, a limit of measuring a client we do
    not control."""
    row = {"answered": bool(answer.strip()) and not declined and not server_declined}
    if label == "one lookup":
        row["role_named"] = "front desk associate" in answer.lower()
    return row


llm_call = llm.call_with_retry  # the unwrapped original


def _temp_jsonl() -> Path:
    fd, name = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)  # the server process writes it by name; this process only reads it
    return Path(name)


def run(size: str, retriever) -> list[dict]:
    hit_chars = SIZES[size]
    retrieval.HIT_CHARS = hit_chars
    rows = []
    audit, guarded_audit = _temp_jsonl(), _temp_jsonl()
    loop = asyncio.new_event_loop()
    client, guarded, guarded_session = None, None, None
    try:  # opened inside the try, so a server that fails to start never leaves the other one running
        client, session = loop.run_until_complete(open_session(hit_chars, audit))
        if size == "real":  # the guarded endpoint always returns whole-record evidence internally
            guarded, guarded_session = loop.run_until_complete(open_session(hit_chars, guarded_audit, toolset="answer"))
        print(json.dumps({"size": size, "mcp_session_start": session, "guarded_session_start": guarded_session}), flush=True)
        for label, question in REQUESTS.items():
            for way in ("1 tool", "2 MCP (stdio)") + (("2b MCP guarded",) if guarded else ()):
                meter = Meter()
                started = time.perf_counter()
                if way == "1 tool":
                    out = way1_tool(question, meter, retriever)
                else:
                    if way == "2b MCP guarded":
                        out = loop.run_until_complete(way2_mcp(question, meter, guarded, guarded_audit,
                                                               CLIENT_SYSTEM, final_tools=False))
                    else:
                        out = loop.run_until_complete(way2_mcp(question, meter, client, audit))
                per_call = out["bytes"]
                rows.append({
                    "size": size, "request": label, "way": way,
                    "model_calls": meter.calls, "capability_calls": out["capability"],
                    "server_counted": out["server_count"], "server_failed": out.get("server_failed"),
                    "server_ms": out.get("server_ms"), "server_tokens": out.get("server_tokens"),
                    "server_turns": out.get("server_turns"),
                    "total_tokens": meter.tokens + (out.get("server_tokens") or 0),
                    "first_turn_tool_calls": meter.first_turn_tool_calls,
                    "seconds": round(time.perf_counter() - started, 1), "tokens": meter.tokens,
                    "bytes_per_response": round(sum(per_call) / len(per_call)) if per_call else 0,
                    "server_declined": out.get("server_declined"),
                    **graded(out["answer"], label, out.get("server_declined") or 0, out.get("declined", False)),
                    **({"mcp_session_start": guarded_session if way == "2b MCP guarded" else session}
                       if way != "1 tool" else {}),
                })
                print(json.dumps(rows[-1]), flush=True)
    finally:
        if client:
            loop.run_until_complete(client.__aexit__(None, None, None))
        if guarded:
            loop.run_until_complete(guarded.__aexit__(None, None, None))
        guarded_audit.unlink(missing_ok=True)
        loop.close()
        audit.unlink(missing_ok=True)
        retrieval.llm.call_with_retry = llm_call
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", choices=["demo", "real", "both"], default="both")
    parser.add_argument("--out", default=str(HERE.parent.parent / "use_case" / "evals" / "tc5_measure.jsonl"))
    args = parser.parse_args()
    retriever = qa.get_retriever()
    rows = []
    for size in (["demo", "real"] if args.size == "both" else [args.size]):
        rows += run(size, retriever)
    meta = {"model": retrieval.CHAT_MODEL, "embed_model": retrieval.EMBED_MODEL,
            "measured_at": time.strftime("%Y-%m-%d %H:%M"), "python": sys.version.split()[0]}
    with open(args.out, "w") as handle:
        for row in rows:
            handle.write(json.dumps({**meta, **row}) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
