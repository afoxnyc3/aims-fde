"""The model call.

One function, one job: take a conversation, stream back the assistant's reply.

Everything provider-specific lives in environment variables, so switching from
OpenAI to Azure to a self-hosted model is a config change, not a code change.
That property matters more than it looks like it does right now -- see the
"Where does this live?" section of the README.
"""

import json
import os
import time

from litellm import (
    APIConnectionError, RateLimitError, ServiceUnavailableError, Timeout,
    completion, decode, encode, token_counter,
)
from openai import APIError

# LiteLLM picks the provider from the model string:
#   "gpt-4.1-mini"                    -> OpenAI
#   "azure/my-deployment"             -> Azure OpenAI
#   "anthropic/claude-sonnet-5"       -> Anthropic
#   "ollama/llama3.2"                 -> a model running on your laptop
#   "openai/my-model" + LLM_API_BASE  -> any OpenAI-compatible server (vLLM, LM Studio, ...)
MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")
API_BASE = os.getenv("LLM_API_BASE")  # only needed for self-hosted / gateway endpoints
EXTRA_HEADERS = json.loads(os.getenv("LLM_EXTRA_HEADERS") or "{}")

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful assistant. Be concise and concrete.",
)


class ReplyError(RuntimeError):
    """A safe, caller-visible failure to obtain usable model text."""


def is_transient(exc: Exception) -> bool:
    """Worth one more attempt: a connection error, rate limit, 503, timeout or any 5xx. Never a 4xx."""
    if isinstance(exc, (APIConnectionError, RateLimitError, ServiceUnavailableError, Timeout)):
        return True
    return (getattr(exc, "status_code", None) or 0) >= 500


def call_with_retry(call, **kwargs):
    """Make one provider call with one retry on a transient error, one second later.

    The caller passes num_retries=0 (or leaves it unset on embedding) so this is the
    only retry: litellm's own (num_retries > 0) needs tenacity, which this app does
    not install, and does not apply is_transient.
    """
    for attempt in range(2):
        try:
            return call(**kwargs)
        except APIError as exc:
            if not is_transient(exc) or attempt == 1:
                raise
            time.sleep(1)


def build_messages(
    message: str, history: list[dict] | None = None, *, system_prompt: str | None = None,
) -> list[dict]:
    """The exact message list sent to the model for this turn.

    Shared by `stream_reply` and `count_tokens` so the count always matches
    what actually goes over the wire.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT if system_prompt is None else system_prompt}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": message})
    return messages


def count_tokens(message: str, history: list[dict] | None = None) -> int:
    """How many prompt tokens this turn will cost, counted before sending.

    Uses LiteLLM's tokenizer lookup for MODEL. For models it can't map
    (self-hosted, custom deployments) it falls back to a generic tokenizer,
    so treat the number as an estimate there.
    """
    return token_counter(model=MODEL, messages=build_messages(message, history))


def truncate_prompt(text: str, max_tokens: int) -> str:
    """Cut `text` down to at most `max_tokens` tokens, keeping the start.

    Counts with MODEL's tokenizer, so the same estimate caveat as
    `count_tokens` applies to models LiteLLM can't map.
    """
    tokens = encode(model=MODEL, text=text)
    if len(tokens) <= max_tokens:
        return text
    return decode(model=MODEL, tokens=tokens[:max_tokens])


def stream_reply(
    message: str, history: list[dict] | None = None, *,
    system_prompt: str | None = None, max_tokens: int | None = None,
    timeout: float | None = None, num_retries: int | None = None,
):
    """Yield the assistant's reply as it arrives, one growing string at a time.

    `history` is a list of {"role": ..., "content": ...} dicts. We rebuild the
    full message list on every turn -- the model is stateless, so the
    conversation only exists because we keep sending it. Token limits, timeout,
    and retries are independent; omitted options retain provider defaults.
    Raise ReplyError for a content-filter stop or an empty text response.
    """
    messages = build_messages(message, history, system_prompt=system_prompt)

    kwargs = {"model": MODEL, "messages": messages, "stream": True}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if timeout is not None:
        kwargs["timeout"] = timeout
    if num_retries is not None:
        kwargs["num_retries"] = num_retries
    if API_BASE:
        kwargs["api_base"] = API_BASE
    if EXTRA_HEADERS:
        kwargs["extra_headers"] = EXTRA_HEADERS

    reply = ""
    for chunk in completion(**kwargs):
        if not chunk.choices:  # Usage-only chunks have no choices.
            continue
        choice = chunk.choices[0]
        if choice.finish_reason == "content_filter":
            raise ReplyError("The model provider declined to answer (content filter).")
        piece = choice.delta.content
        if piece:
            reply += piece
            yield reply
    if not reply.strip():
        raise ReplyError("The model provider returned no text; please try again or review manually.")
