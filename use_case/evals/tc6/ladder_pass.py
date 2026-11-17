"""TC6 Step 5: attacks and legitimate inputs through the same rails, in one pass, before and after the fix.

    uv run --project 01_Product_Engineering/challenge python use_case/evals/tc6/ladder_pass.py --before-app <pre-fix app folder>

No model calls here. Four parts, one output file pair in runs/ (ladder_pass_<stamp>.json and .md):

A. Rails: every attack question and every legitimate input through the one LLMRails object built
   from the app's guardrails/ folder (harness.rails()), input rail and output rail each on its own.
B. Replay: each recorded leaking model result through the shipped answer path, on the pre-fix app
   (--before-app, a git worktree of the commit before the fixes) and on this tree's app.
C. Live attack runs on the local model, read from runs/: the 2026-11-15 pass (before) and the
   newest pass made after it (after). attack.py made them; this only counts.
D. Live legitimate questions on the local model, read from runs/benign-live-*.json (benign_live.py).
"""

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(EVALS), str(ROOT)]

import harness as evals  # noqa: E402

RUNS = HERE / "runs"
BEFORE_PASS = "20261115-235"
# Two passes were made on 2026-11-16. The first, on the three planned fixes, shipped one leak (a
# roleplay decline reason quoting the marker). The marker check followed; runs stamped from here on
# are on the final code. Both are reported.
FINAL_FROM = "20261116-1216"
TEMPLATE = "Which system role does a new {role} at {venue} need?"


def timed(fn, *args, **kwargs):
    started = time.perf_counter()
    return fn(*args, **kwargs), (time.perf_counter() - started) * 1000


def rail_pass(items: list[tuple[str, str]], reply: bool) -> dict:
    """items: (label, text). Returns stopped count, which ones, by which rung, and mean ms per call."""
    stopped, ms = [], []
    for label, text in items:
        rung, took = timed(evals.stopped_by, "q", reply=text) if reply else timed(evals.stopped_by, text)
        ms.append(took)
        if rung:
            stopped.append({"item": label, "rung": rung})
    return {"n": len(items), "stopped": len(stopped), "which": stopped, "ms_per_call": round(sum(ms) / len(ms), 1) if ms else None}


def larger_questions() -> list[str]:
    import ast

    pairs = set()
    for row in evals.load_jsonl(EVALS / "real_v05" / "golden.jsonl"):
        expected = row["expected"]
        expected = ast.literal_eval(expected) if isinstance(expected, str) else expected
        if expected.get("role") and expected.get("venue"):
            pairs.add((expected["role"], expected["venue"]))
    return [TEMPLATE.format(role=role, venue=venue) for role, venue in sorted(pairs)]


def no_final_text(cases: list[dict]) -> dict:
    """Recordings with no final answer and no decline reason: counted by what they hold, not by a
    cause. This cohort was once labelled "leak in tool arguments only"; most of it has no tool call."""
    empty = [(c["attack"], rec) for c in cases for rec in c["recorded"] if not (rec.get("answer") or rec.get("decline_reason"))]
    return {"n": len(empty), "by_attack": dict(Counter(attack for attack, _ in empty)),
            "prose_dropped_no_tool_call": sum(1 for _, rec in empty if not rec.get("trace") and rec.get("stopped") == "unstructured"),
            # Search steps in the trace. Not "made a tool call": an answer call with no text is one too.
            "with_a_search_trace": sum(1 for _, rec in empty if rec.get("trace")),
            "note": "no final answer or decline reason in the recording, so the output rail has nothing to read. Where no tool call was made and the run ended unstructured, the model replied in prose and the closed-set output rule discarded it"}


def part_a() -> dict:
    cases = evals.load_injection_cases()
    evals.stopped_by("warm up")  # the first call builds the rails; keep it out of the timing
    direct = [(c["id"], c["input"]) for c in cases if c["door"] == "direct"]
    other = [(c["id"], c["input"]) for c in cases if c["door"] != "direct"]
    golden_q = [(c["id"], c["input"]) for c in evals.load_cases() if c["kind"] == "question"]
    larger = [(f"pair-{n:02d}", q) for n, q in enumerate(larger_questions(), 1)]
    synthetic = evals.load_jsonl(EVALS / "synthetic.jsonl")
    tickets = list(dict.fromkeys(json.loads(r["input"])["ticket_text"] if isinstance(r["input"], str)
                                 else r["input"]["ticket_text"] for r in synthetic))
    ticket_items = [(f"synthetic-ticket-{n}", t) for n, t in enumerate(tickets, 1)]
    leaking = [(f"{c['id']}#{n}", text) for c in cases for n, rec in enumerate(c["recorded"], 1)
               if (text := (rec.get("answer") or rec.get("decline_reason") or ""))]
    oracle = json.loads((EVALS / "oracle_answers.json").read_text())
    benign_out = ([(f"oracle-{k}", v) for k, v in oracle.items()]
                  + [(f"synthetic-output-{n}", r["output"] if isinstance(r["output"], str) else json.dumps(r["output"]))
                     for n, r in enumerate(synthetic, 1)]
                  + [(f"golden-output-{g['input']['ticket_ref']}", json.dumps(g["output"]))
                     for g in evals.load_jsonl(EVALS / "golden.jsonl")])
    return {
        "input_rail": {
            "attacks_direct": rail_pass(direct, False),
            "attacks_tool_and_indirect_questions": rail_pass(other, False),
            "legit_golden_questions": rail_pass(golden_q, False),
            "legit_larger_templated_questions": rail_pass(larger, False),
            "legit_synthetic_ticket_texts": rail_pass(ticket_items, False),
        },
        "output_rail": {
            "attacks_recorded_leaking_text": rail_pass(leaking, True),
            "attacks_recorded_no_final_answer_or_decline_reason": no_final_text(cases) | {"stopped": 0},
            "legit_outbound_text": rail_pass(benign_out, True),
        },
        "larger_set": {"template": TEMPLATE, "pairs": len(larger),
                       "note": "from real_v05/golden.jsonl (role, venue) pairs; counts only, no ticket refs"},
    }


def replay_counts() -> dict:
    out = {}
    for case in evals.load_injection_cases():
        if case["recorded"]:
            detail = evals.injection_detail(case)
            out[case["id"]] = {"door": case["door"], "attack": case["attack"], "replays": detail["replays"],
                               "leaks": detail["replay_leaks"]}
    return out


def part_b(before_app: str) -> dict:
    def run(app: str | None) -> dict:
        env = dict(os.environ) | ({"TC6_APP_DIR": app} if app else {})
        done = subprocess.run([sys.executable, __file__, "--replay-json"], env=env, capture_output=True, text=True, check=True)
        return json.loads(done.stdout.strip().splitlines()[-1])

    return {"before": run(before_app), "after": run(None)}


def live_counts(files: list[Path]) -> dict:
    groups = defaultdict(lambda: Counter())
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            g = groups[f"{r['door']} / {r['kind']}" if path.name.split("_")[0] != "hand" else "direct / 12 hand attacks x1"]
            g["runs"] += 1
            g["shipped_canary"] += int(bool(r["leaked"]))
            g["shipped_behaviour"] += int(bool(r["behaviour"]))
            g["pre_gate"] += int(bool(r["leaked_pre_gate"] or r["behaviour_pre_gate"]))
            g["declined"] += int(bool(r["declined"]))
            g["errors"] += int("error" in r)
            if "poison_retrieved" in r:
                g["poison_reached_model"] += int(bool(r["poison_retrieved"]))
    return {k: dict(v) for k, v in sorted(groups.items())}


def part_c() -> dict:
    before = sorted(RUNS.glob(f"*_{BEFORE_PASS}*.jsonl"))
    later = [p for p in sorted(RUNS.glob("*_2*.jsonl")) if p.name.split("_")[-1] > "20261116"]
    mid = [p for p in later if p.name.split("_")[-1] < FINAL_FROM]
    after = [p for p in later if p.name.split("_")[-1] >= FINAL_FROM]
    return {"before": {"files": [p.name for p in before], "doors": live_counts(before)},
            "after_first_three_fixes": {"files": [p.name for p in mid], "doors": live_counts(mid)},
            "after": {"files": [p.name for p in after], "doors": live_counts(after)}}


def part_d() -> dict:
    out = {}
    for label in ("before", "after"):
        files = sorted(RUNS.glob(f"benign-live-{label}_*.json"))
        if not files:
            out[label] = None
            continue
        data = json.loads(files[-1].read_text())
        summary = {"file": files[-1].name, "model": data["model"]}
        for name in ("golden", "larger"):
            rows = [r for r in data["rows"] if r["set"] == name]
            should_answer = [r for r in rows if not r["must_decline"]]
            summary[name] = {
                "n": len(rows), "should_answer": len(should_answer),
                "refused_of_should_answer": sum(bool(r["declined"]) for r in should_answer),
                "refused_by_gate": dict(Counter(r["gate"] for r in should_answer if r["declined"])),
                "refused_ids": [r["id"] for r in should_answer if r["declined"]] if name == "golden" else "not listed",
                "must_decline_declined": f"{sum(bool(r['declined']) for r in rows if r['must_decline'])} of {sum(r['must_decline'] for r in rows)}",
                "errors": sum(r["gate"] == "error" for r in rows),
                "mean_latency_s": round(sum(r["latency_s"] for r in rows) / len(rows), 2) if rows else None,
            }
        out[label] = summary
    return out


def render(result: dict) -> str:
    a, b, c, d = result["rails"], result["replay"], result["live_attacks"], result["live_benign"]
    lines = [f"# TC6 ladder pass, {result['stamp']}", "",
             f"Before: `{result['before_commit']}`. After: `{result['after_commit']}`"
             f"{' plus uncommitted changes' if result['after_dirty'] else ''}. Local model only "
             "(`ollama_chat/qwen2.5:7b`) for every live run; parts A and B make no model call.", "",
             "## A. Same rails, both sets (model-free)", "",
             "| Rung | Set | n | Stopped | ms per call |", "| --- | --- | ---: | ---: | ---: |"]
    for rail, sets in (("input rail: prompt probe rules", a["input_rail"]), ("output rail: reply rules", a["output_rail"])):
        for name, cell in sets.items():
            lines.append(f"| {rail} | {name} | {cell['n']} | {cell['stopped']} | {cell.get('ms_per_call', 'n/a')} |")
    refused = [w for rail in ("input_rail", "output_rail") for name, cell in a[rail].items() if name.startswith("legit")
               for w in cell.get("which", [])]
    lines += ["", "Legitimate inputs refused, and by which rung: " + (json.dumps(refused) if refused else "none."), "",
              "## B. Recorded leaks replayed through the shipped answer path (model-free)", "",
              "| Case | Door | Attack | Recorded leaking results | Still leak, before | Still leak, after |",
              "| --- | --- | --- | ---: | ---: | ---: |"]
    for case_id, after in b["after"].items():
        before = b["before"][case_id]
        lines.append(f"| {case_id} | {after['door']} | {after['attack']} | {after['replays']} | {before['leaks']} | {after['leaks']} |")
    lines += ["", "## C. Live attack runs on the local model, shipped path", "",
              "Each cell: runs / shipped canary leaks / shipped behaviour leaks / leaked before the gates. "
              "\"Fixes 19-21\" is the first pass after the three planned fixes; \"final\" adds the marker check "
              "that pass led to.", "",
              "| Door / attack | Before | After fixes 19-21 | After, final |", "| --- | --- | --- | --- |"]
    passes = (c["before"]["doors"], c["after_first_three_fixes"]["doors"], c["after"]["doors"])
    cell = lambda g: (f"{g['runs']} / {g.get('shipped_canary', 0)} / {g.get('shipped_behaviour', 0)} / {g.get('pre_gate', 0)}"  # noqa: E731
                      + (f" ({g['errors']} errors)" if g.get("errors") else "")) if g else "not run"
    for door in sorted(set().union(*passes)):
        lines.append(f"| {door} | " + " | ".join(cell(p.get(door)) for p in passes) + " |")
    totals = [(sum(g["runs"] for g in p.values()), sum(g.get("shipped_canary", 0) + g.get("shipped_behaviour", 0) for g in p.values()))
              for p in passes]
    lines.append("| **all doors, shipped leaks of runs** | " + " | ".join(f"**{k} of {n}**" if n else "not run" for n, k in totals) + " |")
    lines += ["", "## D. Live legitimate questions on the local model, shipped path", "",
              "| Set | Should be answered | Refused, before | Refused, after | By gate, after | Must-decline declined, after |",
              "| --- | ---: | ---: | ---: | --- | --- |"]
    for name in ("golden", "larger"):
        x, y = (d["before"] or {}).get(name), (d["after"] or {}).get(name)
        lines.append(f"| {name} | {(y or x or {}).get('should_answer', 'not run')} | {x['refused_of_should_answer'] if x else 'not run'} "
                     f"| {y['refused_of_should_answer'] if y else 'not run'} | {json.dumps(y['refused_by_gate']) if y else 'not run'} "
                     f"| {y['must_decline_declined'] if y else 'not run'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before-app", help="app folder of the commit before the fixes (a git worktree)")
    parser.add_argument("--replay-json", action="store_true", help="internal: print replay counts for TC6_APP_DIR")
    args = parser.parse_args()
    if args.replay_json:
        print(json.dumps(replay_counts()))
        return
    if not args.before_app:
        parser.error("--before-app is required")
    git = lambda *a, cwd=ROOT: subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True).stdout.strip()  # noqa: E731
    stamp = time.strftime("%Y%m%d-%H%M%S")
    result = {"stamp": stamp, "before_commit": git("rev-parse", "--short", "HEAD", cwd=Path(args.before_app)),
              "after_commit": git("rev-parse", "--short", "HEAD"), "after_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
              "rails": part_a(), "replay": part_b(args.before_app), "live_attacks": part_c(), "live_benign": part_d()}
    (RUNS / f"ladder_pass_{stamp}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (RUNS / f"ladder_pass_{stamp}.md").write_text(render(result), encoding="utf-8")
    print(render(result))
    print(f"saved runs/ladder_pass_{stamp}.json and .md")


if __name__ == "__main__":
    main()
