"""The input rail on the request path (TC6): the NeMo config in guardrails/, input rails only.

qa.answer_question calls stopped_by() before the model. The config names no model and every rung
in it is a rule, so the check makes no model call and sends nothing anywhere. There is no setting
that turns it off: a caller skips it only by passing an argument, and only tests and measurement
scripts do.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

GUARDRAILS = Path(__file__).resolve().parent / "guardrails"
INPUT_ONLY = {"rails": {"input": True, "dialog": False, "output": False, "retrieval": False},
              "log": {"activated_rails": True}}
# Shown to the user when a rung stops the question. Written here, never by a model.
DECLINE = ("The question asks for the assistant's own instructions or tries to change them, so it was "
           "not sent to the model. Ask about onboarding tickets or the access standard.")
GUARD_ERROR = "guard_error"
# The endpoint serves requests on threads. One check at a time: it takes milliseconds.
_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def rails():
    """The one LLMRails object, built from guardrails/ on first use and kept."""
    from nemoguardrails import LLMRails, RailsConfig

    return LLMRails(RailsConfig.from_path(str(GUARDRAILS)))


def _check(question: str) -> str | None:
    with _LOCK:
        response = rails().generate(messages=[{"role": "user", "content": question}], options=INPUT_ONLY)
    return next((rail.name for rail in response.log.activated_rails if rail.stop), None)


def stopped_by(question: str) -> str | None:
    """The rung that stopped the question, or None. Decided from activated_rails, never from wording.

    Fails closed: if the rails cannot be built or run, the answer is "guard_error" and the question
    does not go on. NeMo's sync call refuses to run inside an event loop, so from async code (the
    MCP server) the check runs on a worker thread.
    """
    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _check(question)
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_check, question).result()
    except Exception:
        return GUARD_ERROR
