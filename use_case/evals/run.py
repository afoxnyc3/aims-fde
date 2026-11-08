"""Score echo, oracle and the running endpoint, and print the report.

Start the endpoint first (from 01_Product_Engineering/challenge/), with both
models set if your key is OpenRouter only:

    LLM_MODEL=openrouter/anthropic/claude-sonnet-5.5 RETRIEVAL_MODEL=openrouter/anthropic/claude-sonnet-5.5 uv run python app.py

Then, from the repo root (the challenge env has gradio_client):

    uv run --project 01_Product_Engineering/challenge python use_case/evals/run.py
    uv run --project 01_Product_Engineering/challenge python use_case/evals/run.py --no-endpoint --no-judge   # no model calls

Each endpoint run costs real model calls, one per case. The judge adds 16 calls to
calibrate, plus one per question for each of echo, oracle and the endpoint.

The TC4 baseline itself is on real tickets, whose text and runner stay private, so
it cannot be re-run from this repo. `--committed` reports it from the saved runs
instead, offline, with no model calls and no endpoint:

    python3 use_case/evals/run.py --committed

It prints echo, oracle and the endpoint on the real_v03 dev, test and grid splits
as recorded, then the endpoint's saved outputs rescored against the current labels
(they moved after the runs: the 2026-11-07 name policy), checks that baseline.json
is the committed test run, and compares the two, which
must print PASS. Only a run from the private runner can be compared to
baseline.json: the synthetic suite below has different cases and scorers, so
compare() refuses it. Synthetic runs compare against each other (data/traces/).
"""

import argparse
import copy
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import harness as evals  # noqa: E402  (use_case/evals/harness.py, not helpers.harness)

RUNS_DIR = Path(__file__).parent.parent / "data" / "traces"
BASELINE = Path(__file__).parent / "baseline.json"
COMMITTED = Path(__file__).parent / "real_v03" / "results"
SYSTEMS = ("echo", "oracle", "endpoint")
SPLITS = ("dev", "test", "grid")


def echo(case_input) -> str:
    """Returns the input. If the endpoint does not beat this, something is broken upstream."""
    return json.dumps(case_input) if isinstance(case_input, dict) else case_input


def make_oracle(cases: list[dict]):
    """Returns the reference. If this does not score 1.0 on every scorer, the scorer is wrong.

    The questions' answers are in oracle_answers.json, written from the labels and the
    records. Because they carry the label's terms, they prove the scorers accept a right
    answer containing those terms, not one in other words: that is a job for the judge.
    """
    written = json.loads((Path(__file__).parent / "oracle_answers.json").read_text(encoding="utf-8"))
    answers = {}
    for case in cases:
        ref = case["output"]
        if case["kind"] == "ticket":
            out = ref
        elif ref.get("must_decline"):
            out = {"declined": True, "answer": None, "decline_reason": "No record covers this.", "sources": []}
        else:
            out = {"declined": False, "answer": written[case["id"]], "decline_reason": None, "sources": ref["gold"]}
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


SCENARIOS_NEED_V02 = (
    "--scenarios needs the v0.2 standard: set ONBOARDING_STANDARD to its path here, and start the endpoint with "
    "the same setting. SYN-ASK-002 expects a re-hire to reach review before any ask, and only the v0.2 decision "
    "code (standard_v02.py) has that order; the demo path asks first, so it would fail for a reason that is not "
    "the model's. /health does not report the standard, so this checks this shell only."
)


def scenarios_preflight() -> None:
    if not os.getenv("ONBOARDING_STANDARD"):
        raise SystemExit(SCENARIOS_NEED_V02)


def of(k: int, n: int) -> str:
    return f"{k} of {n} ({k / n:.0%})" if n else f"{k} of 0"


LABEL_FILES = {"dev": "golden.jsonl", "test": "golden.jsonl", "grid": "grid.jsonl"}


def current_labels(split: str, labels_dir: Path = COMMITTED.parent) -> dict[str, dict]:
    """The `expected` block of every label in a split, keyed by ticket_ref, as the label files say today."""
    rows = evals.load_jsonl(labels_dir / LABEL_FILES[split])
    return {row["ticket_ref"]: row["expected"] for row in rows if row["split"] == split or split == "grid"}


def rescore(run: "evals.harness.RunReport", labels: dict[str, dict]) -> "evals.harness.RunReport":
    """The same saved outputs, scored against `labels` instead of the labels at run time. No model calls.

    status_accuracy is the status matching, which reproduces every saved score. Over-access keeps the recorded
    verdict where the label's status did not change, because the private scorer may check more than status; where
    it did change, a recommendation against a label that is not `recommended` is an over-grant.
    """
    out = copy.deepcopy(run)
    for r in out.results:
        if r.error:
            continue
        old, actual = evals.parse(r.expected), evals.parse(r.actual)
        new = {key: labels[r.input].get(key) for key in old}
        r.expected = json.dumps(new, sort_keys=True)
        r.scores["status_accuracy"] = float(actual.get("status") == new["status"])
        if new["status"] != old["status"]:
            r.scores["no_over_privilege"] = 0.0 if actual.get("status") == "recommended" and new["status"] != "recommended" else 1.0
    for key in out.means:
        out.means[key] = sum(r.scores.get(key, 0.0) for r in out.results) / out.n if out.n else 0.0
    out.meta = {**out.meta, "rescored_against": "current labels"}
    out.meta.pop("ci95", None)  # the recorded interval belongs to the recorded scores
    return out


def report_row(system: str, split: str, run) -> str:
    mean = run.means["status_accuracy"]
    recorded = run.meta.get("ci95", {}).get("status_accuracy")
    # Prefer the interval the run recorded when it was scored, so this report and the write-up quote one number.
    low, high = recorded or evals.bootstrap_ci([r.scores["status_accuracy"] for r in run.results])[1:]
    # An errored case scores 0 on everything; count it as an error, not as an over-grant.
    over = sum(r.scores["no_over_privilege"] < 1.0 for r in run.results if not r.error)
    errored = sum(bool(r.error) for r in run.results)
    note = f" ({errored} errored)" if errored else ""
    # Unnecessary: an ask the label did not need. Missed: a recommendation where the label asks. See harness.
    asks, missed, scored = evals.count_asks(run)
    counts = " | ".join(of(k, scored) for k in (over, asks, missed))  # one denominator: the cases scored
    right = sum(r.scores["status_accuracy"] for r in run.results)
    return f"| {system} | {split} | {run.n}{note} | {right:.0f} of {run.n}: {mean:.2f} [{low:.2f}, {high:.2f}] | {counts} |"


HEADER = ["| System | Split | n | status_accuracy (95% CI) | over-access | unnecessary asks | missed asks |",
          "| --- | --- | --- | --- | --- | --- | --- |"]


def committed_report(results_dir: Path = COMMITTED, baseline_path: Path = BASELINE) -> bool:
    """Report the saved real_v03 runs and check the baseline. Returns True if every check passed."""
    lines = list(HEADER)
    for split in SPLITS:
        for system in SYSTEMS:
            lines.append(report_row(system, split, evals.harness.load(results_dir / f"{system}_{split}.json")))
    print("\n".join(lines))

    # The labels have moved since the runs (the 2026-11-07 name policy). Same outputs, today's labels, endpoint only:
    # the saved oracle output is the old label, so rescoring it would only measure the relabel.
    lines = ["\nThe endpoint's saved outputs, rescored against the current labels (no model calls):", *HEADER]
    for split in SPLITS:
        run = evals.harness.load(results_dir / f"endpoint_{split}.json")
        lines.append(report_row("endpoint", split, rescore(run, current_labels(split, results_dir.parent))))
    print("\n".join(lines))

    baseline = evals.harness.load(baseline_path)
    test_run = evals.harness.load(results_dir / "endpoint_test.json")
    same = baseline.fingerprint == test_run.fingerprint and baseline.means == test_run.means
    print(f"\nbaseline.json is {'the' if same else 'NOT the'} committed endpoint test run ({baseline.name}, {baseline.fingerprint}, n={baseline.n})")
    meta = baseline.meta
    print(f"model {meta.get('model')}, standard {meta.get('standard')}, public repo commit {meta.get('repo_commit')} (runner private), run {meta.get('run_at')}")
    comparison = evals.harness.compare(baseline, test_run)
    print(comparison)
    return same and comparison.passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.getenv("TC4_ENDPOINT", "http://127.0.0.1:7860/"))
    parser.add_argument("--no-endpoint", action="store_true", help="echo and oracle only")
    parser.add_argument("--no-judge", action="store_true", help="model-free scorers only; changes the fingerprint, so such a run cannot be compared to a judged synthetic run")
    parser.add_argument("--scenarios", action="store_true", help="the three synthetic multi-turn scenarios against the endpoint (2 model calls each)")
    parser.add_argument("--committed", action="store_true", help="report the saved real_v03 runs and check baseline.json, offline")
    args = parser.parse_args()

    if args.committed:
        raise SystemExit(0 if committed_report() else 1)
    if args.scenarios:
        scenarios_preflight()  # before the import and the endpoint client, so a wrong setup costs nothing
        import scenarios

        endpoint = make_endpoint(args.url)
        # Saved after every turn, so an endpoint failure part-way keeps the turns before it. Gitignored, like the runs.
        path = RUNS_DIR / f"scenarios_{datetime.now():%Y%m%d_%H%M%S}.json"
        report = scenarios.run_all(lambda req: endpoint(json.loads(req)), path)
        for sid, r in zip(report.meta["scenario_ids"], report.results):
            turns = " -> ".join(evals.parse(t).get("status", "?") for t in json.loads(r.actual))
            print(f"{sid}: {r.scores['scenario_pass']:.0f}  turns: {turns or '-'}" + ("  ERRORED" if r.error else ""))
        print(f"{sum(r.scores['scenario_pass'] for r in report.results):.0f} of {report.n} scenarios passed, {report.errors} errored")
        print(f"saved: {path}")
        return

    cases = evals.load_cases()
    scorers = dict(evals.SCORERS)
    if not args.no_judge:
        from helpers.llm import CallStats

        stats = CallStats()
        judge = evals.make_judge(stats)
        calibration = evals.calibrate(judge)
        print(f"judge {evals.JUDGE_MODEL}: {calibration}")
        # Stop rather than save a run without the column: its fingerprint could never be compared to a judged synthetic run.
        if not calibration.passed:
            raise SystemExit("The judge failed calibration, so nothing was run. Fix it, or pass --no-judge and say so.")
        grounded = evals.make_grounded(judge)
        scorers[evals.grounded_label()] = grounded
    reports = [evals.run_eval(cases, echo, "echo", scorers), evals.run_eval(cases, make_oracle(cases), "oracle", scorers)]
    if not args.no_endpoint:
        endpoint = evals.run_eval(cases, make_endpoint(args.url), "endpoint", scorers)
        with urllib.request.urlopen(args.url.rstrip("/") + "/health", timeout=5) as resp:
            endpoint.meta["ticket_model"] = json.load(resp).get("model", "unknown")
        # /health reports LLM_MODEL only. Questions can use RETRIEVAL_MODEL, and each response records which.
        traces = [evals.parse(r.actual).get("trace") or {} for r in endpoint.results]
        endpoint.meta["question_models"] = sorted({t["model"] for t in traces if t.get("model")})
        if not args.no_judge:
            endpoint.meta["judge"] = {"model": evals.JUDGE_MODEL, "calibration": str(calibration), "failures_all_systems": grounded.failures}
        reports.append(endpoint)
        # Gitignored. A number with no saved run behind it cannot be checked later.
        saved = evals.harness.save(endpoint, RUNS_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.json")
        print(f"saved: {saved}")

    if not args.no_judge:
        print(f"judge calls, measured: {stats}")
        if grounded.failures:
            print(f"WARNING: {grounded.failures} judge calls failed and scored 0. Do not read the grounded column as a result.")
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
