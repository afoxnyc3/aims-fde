"""Collect traces from the running endpoint for the TC4 Step 1 read-through.

Sends every question in retrieval.jsonl to `answer_onboarding_question` three
times, and every golden in golden.jsonl to `recommend_onboarding_access` once:
15 x 3 + 6 = 51 traces. Repeats show run-to-run variance on the same input.
Nothing is scored here -- reading the traces and writing failures.md is the
step.

Start the endpoint first (from 01_Product_Engineering/challenge/):

    uv run --env-file ../../.env python app.py

Then, from the repo root (the challenge env has gradio_client; the root env does not):

    uv run --project 01_Product_Engineering/challenge python use_case/evals/collect_traces.py
    uv run --project 01_Product_Engineering/challenge python use_case/evals/collect_traces.py --repeats 1   # 21 traces

Writes to use_case/data/traces/ (gitignored): the raw JSONL and a Markdown
file to read. Each trace costs real model calls.
"""

import argparse
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from gradio_client import Client

HERE = Path(__file__).parent
OUT_DIR = HERE.parent / "data" / "traces"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def plan(repeats: int) -> list[dict]:
    """One job per trace: which endpoint, which input, and the labels you wrote for it."""
    jobs = []
    for q in load_jsonl(HERE / "retrieval.jsonl"):
        for run in range(1, repeats + 1):
            jobs.append({
                "endpoint": "answer_onboarding_question",
                "id": q["id"],
                "run": run,
                "payload": {"question": q["question"]},
                "reference": {k: q[k] for k in ("kind", "gold", "must_decline", "expected_terms", "why") if k in q},
            })
    for i, g in enumerate(load_jsonl(HERE / "golden.jsonl"), start=1):
        jobs.append({
            "endpoint": "recommend_onboarding_access",
            "id": g["input"].get("ticket_ref") or f"golden-{i}",
            "run": 1,
            "payload": g["input"],
            "reference": {"output": g.get("output"), "why": g.get("why")},
        })
    return jobs


def call(url: str, job: dict) -> dict:
    """One request. An error is recorded as the trace -- an operational failure is still a failure."""
    client = Client(url, verbose=False)
    started = time.perf_counter()
    try:
        raw = client.predict(json.dumps(job["payload"]), api_name=f"/{job['endpoint']}")
        output, error = json.loads(raw), None
    except Exception as exc:
        output, error = None, f"{type(exc).__name__}: {exc}"
    return {
        **job,
        "output": output,
        "error": error,
        "latency_s": round(time.perf_counter() - started, 2),
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def render_output(trace: dict) -> list[str]:
    if trace["error"]:
        return [f"**Error:** `{trace['error']}`"]
    out = trace["output"]
    if trace["endpoint"] == "answer_onboarding_question":
        steps = out.get("trace", {}).get("steps", [])
        lines = [
            f"- **declined:** {out.get('declined')}",
            f"- **answer:** {out.get('answer')}",
            f"- **sources:** {', '.join(out.get('sources') or []) or '(none)'}",
        ]
        if out.get("decline_reason"):
            lines.append(f"- **decline_reason:** {out['decline_reason']}")
        if out.get("dropped_citations"):
            lines.append(f"- **dropped_citations:** {', '.join(out['dropped_citations'])}")
        lines.append(f"- **retrieval:** {len(steps)} calls, stopped={out.get('trace', {}).get('stopped')}")
        lines += [f"  - `{s.get('tool')}` {json.dumps(s.get('args'))} -> {s.get('chars')} chars" for s in steps]
        return lines
    lines = [
        f"- **status:** {out.get('status')}  (needs_human={out.get('needs_human')}, review_reason={out.get('review_reason')})",
        f"- **rationale:** {out.get('rationale')}",
    ]
    for key in ("missing_fields", "caveats"):
        if out.get(key):
            lines.append(f"- **{key}:** {'; '.join(out[key])}")
    if out.get("jira_comment"):
        lines.append(f"- **jira_comment:** {out['jira_comment']}")
    if out.get("answer"):
        lines.append(f"- **answer:**\n\n```json\n{json.dumps(out['answer'], indent=1)}\n```")
    return lines


def render_input(trace: dict) -> list[str]:
    if trace["endpoint"] == "answer_onboarding_question":
        return [f"> {trace['payload']['question']}"]
    p = trace["payload"]
    lines = [f"```\n{p.get('ticket_text', '').strip()}\n```"]
    lines += [f"- comment {c.get('created_at')} ({c.get('author_type')}): {c.get('text')}" for c in p.get("comments", [])]
    return lines


def render_markdown(traces: list[dict], model: str) -> str:
    lines = [
        "# Traces for the Step 1 read-through",
        "",
        f"{len(traces)} traces, model `{model}`, collected {traces[0]['at'] if traces else ''}. "
        "Read the output before the reference. One sentence per failure in `Notes`.",
    ]
    for n, t in enumerate(traces, start=1):
        lines += [
            "", "---", "",
            f"## {n}. {t['id']} -- run {t['run']} -- `{t['endpoint']}` ({t['latency_s']}s)",
            "", "**Input**", "", *render_input(t),
            "", "**Output**", "", *render_output(t),
            "", "<details><summary>Reference (your labels)</summary>", "",
            f"```json\n{json.dumps(t['reference'], indent=1)}\n```", "", "</details>",
            "", "**Notes:** ",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:7860/")
    parser.add_argument("--repeats", type=int, default=3, help="runs per question (goldens always run once)")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    try:
        with urllib.request.urlopen(args.url.rstrip("/") + "/health", timeout=5) as resp:
            model = json.load(resp).get("model", "unknown")
    except OSError as exc:
        raise SystemExit(f"Endpoint not reachable at {args.url} ({exc}). Start app.py first.") from None

    jobs = plan(args.repeats)
    print(f"{len(jobs)} traces against {args.url} (model {model}), {args.workers} at a time")
    traces = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n, trace in enumerate(pool.map(lambda j: call(args.url, j), jobs), start=1):
            traces.append(trace)
            print(f"  {n:>2}/{len(jobs)} {trace['id']} run {trace['run']}: {'ERROR' if trace['error'] else 'ok'} ({trace['latency_s']}s)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = OUT_DIR / f"traces_{stamp}.jsonl"
    md_path = OUT_DIR / f"traces_{stamp}.md"
    jsonl_path.write_text("".join(json.dumps(t) + "\n" for t in traces), encoding="utf-8")
    md_path.write_text(render_markdown(traces, model), encoding="utf-8")

    errors = sum(1 for t in traces if t["error"])
    print(f"\n{len(traces)} traces, {errors} errors")
    print(f"raw:  {jsonl_path}")
    print(f"read: {md_path}")


if __name__ == "__main__":
    main()
