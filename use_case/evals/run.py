"""Score echo, oracle and the running endpoint, and print the report.

Start the endpoint first (from 01_Product_Engineering/challenge/), with both
models set if your key is OpenRouter only:

    LLM_MODEL=openrouter/anthropic/claude-sonnet-5.5 RETRIEVAL_MODEL=openrouter/anthropic/claude-sonnet-5.5 uv run python app.py

Then, from the repo root (the challenge env has gradio_client):

    uv run --project 01_Product_Engineering/challenge python use_case/evals/run.py
    uv run --project 01_Product_Engineering/challenge python use_case/evals/run.py --no-endpoint --no-judge   # no model calls

Each endpoint run costs real model calls, one per case. The judge adds 16 calls to
calibrate, plus one per question for each of echo, oracle and the endpoint.
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import harness as evals  # noqa: E402  (use_case/evals/harness.py, not helpers.harness)

RUNS_DIR = Path(__file__).parent.parent / "data" / "traces"


def echo(case_input) -> str:
    """Returns the input. If the endpoint does not beat this, something is broken upstream."""
    return json.dumps(case_input) if isinstance(case_input, dict) else case_input


def make_oracle(cases: list[dict]):
    """Returns the reference. If this does not score 1.0 on every scorer, the scorer is wrong.

    The questions have no written reference answer, so their oracle is built from the
    labels. It proves the scorers accept a right answer containing those terms. It
    cannot prove they accept one in other words: that is a job for the judge.
    """
    answers = {}
    for case in cases:
        ref = case["output"]
        if case["kind"] == "ticket":
            out = ref
        elif ref.get("must_decline"):
            out = {"declined": True, "answer": None, "decline_reason": "No record covers this.", "sources": []}
        else:
            terms = [t[0] if isinstance(t, list) else t for t in ref["expected_terms"]]
            out = {"declined": False, "answer": "Reference: " + "; ".join(terms), "decline_reason": None, "sources": ref["gold"]}
        answers[json.dumps(case["input"], sort_keys=True)] = json.dumps(out)
    return lambda case_input: answers[json.dumps(case_input, sort_keys=True)]


def make_endpoint(url: str):
    from gradio_client import Client

    client = Client(url, verbose=False)

    def call(case_input) -> str:
        if isinstance(case_input, dict):
            return client.predict(json.dumps(case_input), api_name="/recommend_onboarding_access")
        return client.predict(json.dumps({"question": case_input}), api_name="/answer_onboarding_question")

    return call


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.getenv("TC4_ENDPOINT", "http://127.0.0.1:7860/"))
    parser.add_argument("--no-endpoint", action="store_true", help="echo and oracle only")
    parser.add_argument("--no-judge", action="store_true", help="model-free scorers only; changes the fingerprint, so such a run cannot be compared to the baseline")
    args = parser.parse_args()

    cases = evals.load_cases()
    scorers = dict(evals.SCORERS)
    if not args.no_judge:
        from helpers.llm import CallStats

        stats = CallStats()
        judge = evals.make_judge(stats)
        calibration = evals.calibrate(judge)
        print(f"judge {evals.JUDGE_MODEL}: {calibration}")
        # A failed judge is reported and left out. score() would raise, and helpers.harness would turn that into zeros.
        if calibration.passed:
            scorers["grounded"] = evals.make_grounded(judge)
    reports = [evals.run_eval(cases, echo, "echo", scorers), evals.run_eval(cases, make_oracle(cases), "oracle", scorers)]
    if not args.no_endpoint:
        endpoint = evals.run_eval(cases, make_endpoint(args.url), "endpoint", scorers)
        with urllib.request.urlopen(args.url.rstrip("/") + "/health", timeout=5) as resp:
            endpoint.meta["ticket_model"] = json.load(resp).get("model", "unknown")
        # /health reports LLM_MODEL only. Questions can use RETRIEVAL_MODEL, and each response records which.
        traces = [evals.parse(r.actual).get("trace") or {} for r in endpoint.results]
        endpoint.meta["question_models"] = sorted({t["model"] for t in traces if t.get("model")})
        reports.append(endpoint)
        # Gitignored. A number with no saved run behind it cannot be checked later.
        saved = evals.harness.save(endpoint, RUNS_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.json")
        print(f"saved: {saved}")

    if not args.no_judge:
        print(f"judge calls, measured: {stats}")
    print(f"{len(cases)} cases\n")
    print(evals.report(reports))
    for run in reports:
        scores = [r.scores["correct_behaviour"] for r in run.results]
        mean, low, high = evals.bootstrap_ci(scores)
        print(f"\n{run.name}: correct_behaviour {mean:.2f}, 95% CI [{low:.2f}, {high:.2f}], n={len(scores)}, {run.errors} errors")
        missed = [c["id"] for c, s in zip(cases, scores) if s < 1.0]
        if run.name != "echo" and missed:
            print("  missed: " + ", ".join(missed))


if __name__ == "__main__":
    main()
