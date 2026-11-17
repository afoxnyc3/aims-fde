"""TC6 Docker check, in two modes that cannot be mixed. Nothing runs on import.

    python /check/docker_check.py attack "TEXT"   # rail proof: is TEXT declined by the input rail?
    python /check/docker_check.py benign N        # question N of the fixed BENIGN list, on the container's model

attack: every model and retrieval entry point is replaced by one that raises, so the text can go
no further than the input rail whatever model the container is pointed at. Exit 0 only if the rail
declined it and nothing tried to call a model; exit 1 if the rail let it through (the call was
blocked, not made). It refuses to start (exit 2) when a provider credential variable is set (API
keys, and the AWS, Azure and Google names; by variable name only, see hosted_keys). It needs
no key and no network: run it with `--network none` and no env file (see README.md, "Docker").

benign: takes no free text. The argument is an index into BENIGN, questions copied from the golden
set (retrieval.jsonl) and the templated set (ladder_pass.TEMPLATE). Anything else is refused
(exit 2) before the app is imported, so this mode cannot carry an attack string to a model.
"""
import contextlib
import json
import os
import re
import sys
from unittest.mock import patch

# Fixed and benign. q02, q04, q13 and q15 of retrieval.jsonl, then one templated question.
BENIGN = (
    "Hospitality Associate Level 1: what role do I use?",
    "The form says login required for a Cafe Associate. Do we create a login?",
    "What access does a housekeeping manager receive within the club-management system?",
    "What access would a level 3 personal trainer receive?",
    "Which system role does a new Lifeguard at Club C need?",
)
USAGE = f'usage: docker_check.py attack "TEXT" | docker_check.py benign N   (N is 0 to {len(BENIGN) - 1})'
# Every way the app reaches a model or builds what does: (module, attribute).
FORBIDDEN = (("litellm", "completion"), ("litellm", "acompletion"), ("litellm", "embedding"),
             ("litellm", "aembedding"), ("llm", "completion"), ("llm", "call_with_retry"), ("retrieval", "ask"),
             ("retrieval", "chat_turn"), ("qa", "get_retriever"))


class ModelCallForbidden(RuntimeError):
    """Attack mode reached a model or retrieval entry point. The call was not made."""


@contextlib.contextmanager
def forbid_model_calls(attempted: list[str]):
    """Inside the block every entry point in FORBIDDEN raises, and its name is added to `attempted`
    first, so an attempt is counted even if the caller catches the error."""
    import importlib

    def forbidden(name):
        def raiser(*args, **kwargs):
            attempted.append(name)
            raise ModelCallForbidden(f"{name} was called in attack mode")
        return raiser

    with contextlib.ExitStack() as stack:
        for module, attribute in FORBIDDEN:
            stack.enter_context(patch.object(importlib.import_module(module), attribute, forbidden(f"{module}.{attribute}")))
        yield


# Names the common providers read a credential from: OpenAI-style keys, AWS (Bedrock), Azure, Google
# (Vertex), Hugging Face, Replicate, watsonx. A check on variable names only: a credential in a file
# (~/.aws/credentials, a default gcloud login) or an instance role is not seen. What stops a call in
# attack mode is forbid_model_calls, not this list.
_CREDENTIAL = re.compile(
    r"_(API_?KEY|API_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|AD_TOKEN|CLIENT_SECRET|CREDENTIALS)$"
    r"|^(AWS_BEARER_TOKEN_BEDROCK|AWS_PROFILE|AWS_WEB_IDENTITY_TOKEN_FILE|HF_TOKEN|HUGGINGFACE_HUB_TOKEN)$")


def hosted_keys() -> list[str]:
    """Non-empty environment variables whose name is a provider credential name."""
    return sorted(k for k, v in os.environ.items() if v and _CREDENTIAL.search(k.upper()))


def attack(text: str) -> int:
    import inputrail
    import qa
    import retrieval
    from qa_schema import QuestionRequest

    keys = hosted_keys()  # read after the imports: litellm loads a .env file when it is imported
    if keys:
        print(f"refused: attack mode does not run with a provider credential in the environment ({len(keys)} found)", file=sys.stderr)
        return 2
    print("mode attack | model", retrieval.CHAT_MODEL, "| hosted keys in env: [] | model calls: forbidden")
    attempted, out, blocked = [], None, False
    with forbid_model_calls(attempted):
        try:
            out = qa.answer_question(QuestionRequest(question=text))
        except ModelCallForbidden:
            blocked = True
        rung = inputrail.stopped_by(text)
    # A rail that could not run also declines ("guard_error"). That is not proof a rule stopped the text.
    broken = rung == inputrail.GUARD_ERROR
    declined = bool(out and out.declined and out.trace.stopped == "input_rail" and rung and not broken and not attempted)
    print(json.dumps({
        "declined": out.declined if out else None, "decline_reason": out.decline_reason if out else None,
        "stopped": out.trace.stopped if out else None, "rung": rung, "model_calls_attempted": attempted,
        "model_calls_made": 0,
        "verdict": "declined by the input rail; no model call attempted" if declined
        else "THE RAIL COULD NOT RUN; not a rail proof" if broken
        else "NOT STOPPED BY THE RAIL; the model call was blocked" if blocked or attempted
        else "NOT DECLINED BY THE INPUT RAIL",
    }, indent=1))
    return 0 if declined else 1


def benign(index: int) -> int:
    import inputrail
    import litellm
    import qa
    import retrieval
    from qa_schema import QuestionRequest

    question = BENIGN[index]
    print("mode benign | question", index, "| model", retrieval.CHAT_MODEL, "| api_base", os.getenv("LLM_API_BASE"),
          "| hosted keys in env:", len(hosted_keys()))
    real, calls = litellm.completion, []

    def spy(*args, **kwargs):
        calls.append(kwargs.get("model"))
        return real(*args, **kwargs)

    with patch.object(litellm, "completion", spy):
        out = qa.answer_question(QuestionRequest(question=question))
    print(json.dumps({"question": question, "declined": out.declined, "decline_reason": out.decline_reason,
                      "stopped": out.trace.stopped, "steps": len(out.trace.steps), "model_calls": len(calls),
                      "rung": inputrail.stopped_by(question)}, indent=1))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "attack":
        return attack(argv[1])
    # An index is ASCII digits only and in range. No other text gets as far as an import of the app.
    if len(argv) == 2 and argv[0] == "benign" and argv[1].isascii() and argv[1].isdigit() and int(argv[1]) < len(BENIGN):
        return benign(int(argv[1]))
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())  # the app folder: the script is mounted outside it
    sys.exit(main(sys.argv[1:]))
