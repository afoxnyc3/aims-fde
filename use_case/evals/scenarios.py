"""Three multi-turn scenarios that open on an intake with no name. Synthetic only.

Each scenario in scenarios.jsonl has a goal, what the agent `knows`, `success` and `must_not`,
the turns, and the expected outcome per turn. All names, emails and ids are invented (SYN-ASK-*).

What the endpoint supports. recommend_onboarding_access is stateless: one Request in, one Response
out, no session and no follow-up turn. A "turn" here is therefore the SAME ticket re-sent with every
comment so far, the way the service desk would re-trigger it after a reply. Turn 2 carries the
later comment in Request.comments (author_type human, trusted id and timestamp). What this covers:
the agent re-reading a ticket after a reply. What it does not: memory of its own earlier ask (the
endpoint never sees turn 1's Response), a reply in a chat thread, or a field edit on the form.

    uv run --project 01_Product_Engineering/challenge python use_case/evals/run.py --scenarios   # model calls
"""

import json
import time
import traceback
from pathlib import Path

from harness import parse  # use_case/evals/harness.py: the same reading of a reply as the TC4 scorers and run.py

HERE = Path(__file__).parent


def load_scenarios() -> list[dict]:
    return [json.loads(line) for line in (HERE / "scenarios.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def requests(scenario: dict) -> list[dict]:
    """One Request per turn: the first turn's ticket, plus every comment up to that turn."""
    first, comments, out = scenario["turns"][0], [], []
    for turn in scenario["turns"]:
        comments = comments + turn.get("comments", [])
        out.append({"ticket_ref": first["ticket_ref"], "ticket_text": first["ticket_text"], "comments": list(comments)})
    return out


def _asked(out: dict, want: dict) -> bool:
    """A first turn that asks: needs_information, naming what it needs, with no proposal."""
    return (out.get("status") == "needs_information" and not out.get("answer")
            and set(want.get("missing_fields_include", [])) <= set(out.get("missing_fields") or []))


def _reviewed(out: dict, want: dict) -> bool:
    """Review for the expected reason, no proposal, and every fact still missing handed over twice: as data in
    review_missing_fields, and by name in the comment the reviewer reads.

    A turn that still has missing facts (handoff_names) must carry no standard_proposal either: a baseline
    built before the name is known is a tier for nobody, or for an invented person. Once the facts are in,
    the baseline is allowed again.
    """
    gaps = want.get("handoff_names", [])
    return (out.get("status") == "human_review" and out.get("review_reason") == want["review_reason"] and not out.get("answer")
            and set(gaps) <= set(out.get("review_missing_fields") or [])
            and all(name in (out.get("jira_comment") or "") for name in gaps)
            and not (gaps and out.get("standard_proposal")))


def name_in_follow_up(turns: list[str], scenario: dict) -> float:
    first, second = (parse(t) for t in turns)
    answer = second.get("answer") or {}
    return float(_asked(first, scenario["expected"][0]) and second.get("status") == "recommended"
                 and answer.get("person_name") == scenario["expected"][1]["person_name"])


def rehire_reaches_review(turns: list[str], scenario: dict) -> float:
    """Review on both turns: never an ask first, and the name arriving never unlocks a recommendation."""
    first, second = (parse(t) for t in turns)
    return float(_reviewed(first, scenario["expected"][0]) and _reviewed(second, scenario["expected"][1]))


def mirror_refused(turns: list[str], scenario: dict) -> float:
    """Refused, not copied: review with no answer, and the colleague is named in no proposal."""
    first, second = (parse(t) for t in turns)
    # Proposals only: the review comment may rightly quote the request. ensure_ascii=False so an accented name still matches.
    proposals = json.dumps([second.get("answer"), second.get("standard_proposal")], ensure_ascii=False)
    return float(_asked(first, scenario["expected"][0]) and _reviewed(second, scenario["expected"][1])
                 and scenario["mirrored"] not in proposals)


SCORERS = {"SYN-ASK-001": name_in_follow_up, "SYN-ASK-002": rehire_reaches_review, "SYN-ASK-003": mirror_refused}
TURNS = 2  # every scorer above reads exactly two turns


class ScenarioError(Exception):
    """The scenario or its scorer is wrong, not the endpoint. run_all records it like any error, under this name."""


def check(scenario: dict) -> None:
    """Fail before any model call when a scenario cannot be scored, rather than after spending its calls."""
    if scenario["id"] not in SCORERS:
        raise ScenarioError(f"{scenario['id']}: no scorer")
    if not len(scenario["turns"]) == len(scenario["expected"]) == TURNS:
        raise ScenarioError(f"{scenario['id']}: {len(scenario['turns'])} turns and {len(scenario['expected'])} expected "
                            f"outcomes, and its scorer reads exactly {TURNS}")


def run_scenario(system, scenario: dict, on_turn=None) -> dict:
    """Send each turn to `system` (Request JSON -> Response JSON) and score the whole conversation.

    on_turn(turns) runs after every reply, so a caller can save before the next model call can fail.
    """
    check(scenario)
    turns = []
    for req in requests(scenario):
        turns.append(system(json.dumps(req)))
        if on_turn:
            on_turn(turns)
    try:
        score = SCORERS[scenario["id"]](turns, scenario)
    except Exception as exc:  # the endpoint answered; say so, rather than leave a traceback that reads as its failure
        raise ScenarioError(f"{scenario['id']}: the scorer failed after every turn was answered: {exc!r}") from exc
    return {"id": scenario["id"], "turns": turns, "score": score}


def run_all(system, path, scenario_list: list[dict] | None = None):
    """Every scenario through helpers.harness.save, written again after each turn.

    One Result per scenario: `actual` is the JSON list of replies so far. An endpoint error marks that
    scenario errored and scores 0, as helpers.harness.run does, and the turns before it stay on disk. The
    saved mean covers finished scenarios only, and meta["finished"] says how many that is.
    """
    from helpers import harness

    scenario_list = scenario_list if scenario_list is not None else load_scenarios()
    cases = [{"input": requests(s), "output": s["expected"]} for s in scenario_list]
    scorers = {"scenario_pass": None}  # fingerprint() reads only the names
    report = harness.RunReport(name="scenarios", fingerprint=harness.fingerprint(cases, scorers),
                               n=len(scenario_list), meta={"scorers": sorted(scorers), "scenario_ids": [s["id"] for s in scenario_list]})

    finished = []

    def save():
        report.meta["finished"] = len(finished)
        report.means = {"scenario_pass": sum(r.scores["scenario_pass"] for r in finished) / len(finished)} if finished else {}
        harness.save(report, path)

    for index, (scenario, case) in enumerate(zip(scenario_list, cases)):
        started = time.perf_counter()
        result = harness.Result(index=index, input=json.dumps(case["input"]), expected=json.dumps(case["output"]),
                                actual="[]", scores={"scenario_pass": 0.0})
        report.results.append(result)

        def on_turn(turns):
            result.actual = json.dumps(turns)
            save()

        try:
            result.scores["scenario_pass"] = run_scenario(system, scenario, on_turn)["score"]
        except Exception:
            result.error = traceback.format_exc(limit=3)
            report.errors += 1
        result.seconds = time.perf_counter() - started
        finished.append(result)
        save()
    return report


def make_oracle(scenario: dict):
    """Replies with each turn's expected outcome. If this does not score 1.0, the scorer is wrong."""
    replies = []
    for want in scenario["expected"]:
        out = {"status": want["status"], "missing_fields": want.get("missing_fields_include", []),
               "review_reason": want.get("review_reason"), "answer": None,
               "review_missing_fields": want.get("handoff_names", []),
               "jira_comment": "Missing from the intake: " + ", ".join(want.get("handoff_names", []))}
        if want["status"] == "recommended":
            out["answer"] = {"person_name": want["person_name"]}
        replies.append(json.dumps(out))
    it = iter(replies)
    return lambda _req: next(it)
