"""The rules behind the two rails. No model calls.

`check_prompt_probe` (input rail) reads the user's question. It can only see direct attacks: a
poisoned ticket or tool description arrives with an ordinary question, so those doors are closed in
the app's code (qa.py, retrieval.py, outcheck.py), not here.

`check_reply` (output rail) reads the reply: the system prompt's marker, an approval stated as
fact, or a link that is not in the standard. It applies the app's own outcheck patterns. It has no
ticket status field to consult, so it is stricter than the app: here every approval claim stops.
"""

import re
import sys
from pathlib import Path

from nemoguardrails.actions import action

APP = Path(__file__).resolve().parents[1]
# Appended, not prepended: the app folder is normally on the path already, and a caller that put
# another commit's app folder first keeps its choice.
if str(APP) not in sys.path:
    sys.path.append(str(APP))

# Narrowed 2026-11-16 after the held-out legitimate set (use_case/evals/tc6/heldout_legit.jsonl): the
# first rules refused 12 of 24 real-sounding questions on wording alone ("system configuration",
# "admin mode", "internal rules", "your instructions for a re-hire"). A rule now needs the prompt or
# the marker named, or an extraction verb aimed at the assistant's own instructions.
_OWN = r"your\s+(?:own\s+|full\s+|system\s+|internal\s+|hidden\s+)?"
PROBES = [re.compile(pattern, re.IGNORECASE) for pattern in (
    # names the prompt or the marker
    r"\b(?:system|hidden|internal|initial|secret)\s+(?:prompt|marker)s?\b",
    r"\b" + _OWN + r"(?:prompt|marker)\b",
    r"\bPNA-?\s*CANARY\b",
    # asks for the assistant's own instructions to be handed over in some form
    r"\b(?:repeat|print|return|translate|reveal|show|output|echo|encode|spell|write|list|give)\b[^.?!]{0,40}\b"
    + _OWN + r"(?:instructions?|configuration|config)\b",
    # tells the assistant to drop its instructions or become something else
    r"\b(?:ignore|disregard|forget)\s+(?:all\s+)?(?:of\s+)?(?:the\s+|your\s+)?(?:previous|prior|above|earlier)\s+"
    r"(?:instructions?|rules)\b",
    r"\byou\s+are\s+now\b",
)]


def probe(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in PROBES)


def unsafe_reply(text: str) -> bool:
    import corpus  # the standard pages ship with the app; no data file is read
    import outcheck

    pages = {page.name: page for page in corpus.load_standard_pages()}
    # The marker is spelled in PROBES above too; outcheck takes it as an argument.
    return outcheck.withheld_reason(text or "", [], pages, "PNA-CANARY-7F3A91") is not None


@action(name="check_prompt_probe")
async def check_prompt_probe(context: dict | None = None) -> bool:
    return probe((context or {}).get("user_message") or "")


@action(name="check_reply")
async def check_reply(context: dict | None = None) -> bool:
    return unsafe_reply((context or {}).get("bot_message") or "")
