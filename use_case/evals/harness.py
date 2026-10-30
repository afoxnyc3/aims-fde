"""The TC4 scorers, over the two endpoints the charter defines.

A case is one question from retrieval.jsonl or one settled golden from
golden.jsonl. A scorer takes the endpoint's raw JSON string and the case, and
returns 0 to 1. Every scorer names the failures.md line it catches.

helpers.harness keeps the run as an artifact. This file holds what is specific
to this project: the cases, the definition of correct, and the report.
"""

import json
import random
import re
from pathlib import Path

from helpers import harness

HERE = Path(__file__).parent

# DEMO-006 is an open policy question, not a settled target (see failures.md).
UNSETTLED = {"DEMO-006"}
# Fields a proposal must get right. Wording and proposed_changes text are not here:
# those are prose, and the standard decides access through these.
PROPOSAL_KEYS = ("person_name", "job_title", "start_date", "login_email", "assignments", "permissions", "venues", "standard_version", "person_id", "matrix_entry_id")
# What a golden's required caveat must say: its subject, and that the value was changed.
MUST_CAVEAT = {"DEMO-001": re.compile(r"(start date|first day).*(differ|moved|changed|correct|comment|title)", re.IGNORECASE)}
# A refusal sitting in `answer`, checked in its opening. "I can't confirm" stays out: q05's honest answer starts that way.
REFUSAL = re.compile(r"\b(can't|can’t|cannot|won't|unable to)\s+(give|provide|share|help)\b", re.IGNORECASE)
REFUSAL_WINDOW = 80
# retrieval.decline_reason cuts at this length, so a reason this long has lost its ending.
REASON_CAP = 300
SENTENCE_END = (".", "!", "?", ")", "]", "`", '"', "”")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_cases() -> list[dict]:
    cases = []
    for q in load_jsonl(HERE / "retrieval.jsonl"):
        reference = {k: q[k] for k in ("gold", "must_decline", "expected_terms") if k in q}
        cases.append({"id": q["id"], "kind": "question", "input": q["question"], "output": reference})
    for g in load_jsonl(HERE / "golden.jsonl"):
        ref = g["input"]["ticket_ref"]
        if ref not in UNSETTLED:
            cases.append({"id": ref, "kind": "ticket", "input": g["input"], "output": g["output"]})
    return cases


def parse(actual: str) -> dict:
    """The endpoint's JSON as a dict. Anything else, echo included, is an empty dict and scores 0."""
    try:
        out = json.loads(actual)
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def normalise(text: str) -> str:
    return (text or "").lower().replace("_", " ").replace("-", " ").replace("’", "'")


def has_term(answer: str, term: str | list[str]) -> bool:
    """A term is a phrase, or a list of phrasings where any one will do. As in measure_retrieval.py, which does not fold hyphens or curly quotes."""
    options = term if isinstance(term, list) else [term]
    return any(normalise(option) in normalise(answer) for option in options)


def question_correct(out: dict, ref: dict) -> bool:
    if ref.get("must_decline"):
        # The reason is what the associate reads on a decline, so a forbidden phrase counts there too.
        said = f"{out.get('answer') or ''} {out.get('decline_reason') or ''}"
        return out.get("declined") is True and not any(has_term(said, t) for t in ref["expected_terms"])
    return out.get("declined") is False and bool(out.get("answer")) and all(has_term(out["answer"], t) for t in ref["expected_terms"])


def ticket_correct(out: dict, gold: dict) -> bool:
    if out.get("status") != gold["status"]:
        return False
    if any(key in gold and out.get(key) != gold[key] for key in ("review_reason", "missing_fields")):
        return False
    for part in ("answer", "standard_proposal"):
        expected, actual = gold.get(part), out.get(part)
        # A proposal where the golden has none is an access recommendation that should have been withheld.
        if bool(expected) != bool(actual):
            return False
        if not expected:
            continue
        if any(actual.get(key) != expected.get(key) for key in PROPOSAL_KEYS):
            return False
        # Goldens omit staff_groups when there are none, and the schema defaults it to empty.
        if (actual.get("staff_groups") or []) != (expected.get("staff_groups") or []):
            return False
    return True


# failures.md line 2: declines a question the status rule routes to human review.
# Also the headline. Tickets count too, because a wrong status is the same failure for the associate.
def correct_behaviour(actual: str, case: dict) -> float:
    out = parse(actual)
    return float(question_correct(out, case["output"]) if case["kind"] == "question" else ticket_correct(out, case["output"]))


# failures.md line 2: every one of those declines returns no sources, so the record never reaches the associate.
def gold_cited(actual: str, case: dict) -> float:
    gold = case["output"].get("gold") or []
    if not gold:
        return 1.0
    sources = parse(actual).get("sources") or []
    return sum(page in sources for page in gold) / len(gold)


# failures.md line 1: the decline reason is cut mid-word.
def reason_intact(actual: str, case: dict) -> float:
    out = parse(actual)
    if not out.get("declined"):
        return 1.0
    reason = (out.get("decline_reason") or "").rstrip()
    return float(len(reason) < REASON_CAP and reason.endswith(SENTENCE_END))


# failures.md line 5: a refusal returned as though it were an answer.
def flag_honest(actual: str, case: dict) -> float:
    if case["kind"] != "question":
        return 1.0
    out = parse(actual)
    if case["output"].get("must_decline"):
        return float(out.get("declined") is True)
    if not out:
        return 0.0
    return float(not REFUSAL.search((out.get("answer") or "")[:REFUSAL_WINDOW]))


# failures.md line 7: a corrected value with no caveat saying it was corrected.
def caveat_present(actual: str, case: dict) -> float:
    pattern = MUST_CAVEAT.get(case["id"])
    if not pattern:
        return 1.0
    return float(any(pattern.search(caveat) for caveat in parse(actual).get("caveats") or []))


SCORERS = {
    "correct_behaviour": correct_behaviour,
    "gold_cited": gold_cited,
    "reason_intact": reason_intact,
    "flag_honest": flag_honest,
    "caveat_present": caveat_present,
}

# Which cases each scorer actually tests. The others return a vacuous 1.0, because the oracle
# has to reach 1.0 and helpers.harness has no "skip". Report these denominators, not the raw mean.
APPLIES = {
    "correct_behaviour": lambda case, out: True,
    "gold_cited": lambda case, out: bool(case["output"].get("gold")),
    "reason_intact": lambda case, out: bool(out.get("declined")),
    "flag_honest": lambda case, out: case["kind"] == "question",
    "caveat_present": lambda case, out: case["id"] in MUST_CAVEAT,
}


def run_eval(cases: list[dict], system, name: str) -> harness.RunReport:
    """helpers.harness.run, plus each scorer's mean over only the cases it tests."""
    raw = []

    def recording(case_input) -> str:
        raw.append("")
        raw[-1] = system(case_input)
        return raw[-1]

    report = harness.run(cases, recording, SCORERS, name=name)
    # helpers.harness caps `actual` at 2,000 characters, which breaks a long ticket's JSON. Keep the whole response.
    for result, text in zip(report.results, raw):
        result.actual = text
    report.meta["applicable"] = {}
    for label, applies in APPLIES.items():
        scores = [r.scores[label] for case, text, r in zip(cases, raw, report.results) if applies(case, parse(text))]
        report.meta["applicable"][label] = {"n": len(scores), "mean": sum(scores) / len(scores) if scores else None}
    return report


def bootstrap_ci(scores: list[float], n_resamples: int = 5000, level: float = 0.95, seed: int = 0) -> tuple[float, float, float]:
    """Mean and percentile interval, by resampling the cases. The same method as Session 7, without numpy."""
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(scores, k=len(scores))) / len(scores) for _ in range(n_resamples))
    tail = (1 - level) / 2
    return sum(scores) / len(scores), means[int(tail * n_resamples)], means[int((1 - tail) * n_resamples) - 1]


def report(reports: list[harness.RunReport]) -> str:
    """One row per system, one column per scorer, each cell with the cases it tested."""
    lines = ["| System | " + " | ".join(SCORERS) + " |", "| --- |" + " --- |" * len(SCORERS)]
    for run in reports:
        cells = []
        for label in SCORERS:
            cell = run.meta["applicable"][label]
            cells.append("n/a (0)" if cell["mean"] is None else f"{cell['mean']:.2f} ({cell['n']})")
        lines.append(f"| {run.name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
