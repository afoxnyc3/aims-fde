"""TC6 Step 5, ship rule D5: the held-out legitimate questions through the input rail, with the
direct attacks and the golden questions in the same pass so the numbers cannot drift.

    uv run --project 01_Product_Engineering/challenge python use_case/evals/tc6/heldout_pass.py

No model call: the rail is rules. Writes runs/heldout-legit_<stamp>.json and never overwrites one.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(EVALS), str(ROOT)]

import harness as evals  # noqa: E402


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


def rail_pass(items: list[tuple[str, str]]) -> dict:
    stopped = [{"item": label, "rung": rung, "text": text} for label, text in items if (rung := evals.stopped_by(text))]
    return {"n": len(items), "stopped": len(stopped), "which": stopped}


def direct_attacks() -> list[tuple[str, str]]:
    """The distinct direct attack questions in attacks.jsonl, in file order. Ids only in the output."""
    inputs = list(dict.fromkeys(row["input"] for row in evals.load_jsonl(EVALS / "attacks.jsonl") if row["kind"] == "direct"))
    return [(f"direct-{n:02d}", text) for n, text in enumerate(inputs, 1)]


def main() -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = HERE / "runs" / f"heldout-legit_{stamp}.json"
    if out.exists():
        sys.exit(f"{out} exists; not overwriting")
    heldout = [(row["id"], row["question"]) for row in evals.load_jsonl(HERE / "heldout_legit.jsonl")]
    golden = [(c["id"], c["input"]) for c in evals.load_cases() if c["kind"] == "question"]
    evals.stopped_by("warm up")
    attacks = rail_pass(direct_attacks())
    for hit in attacks["which"]:
        del hit["text"]  # attack text stays in attacks.jsonl; the run file names the row
    result = {
        "stamp": stamp,
        "commit": git("rev-parse", "--short", "HEAD"),
        "rules_dirty": bool(git("status", "--short", "--", "01_Product_Engineering/challenge/guardrails")),
        "rung": "input rail: prompt probe rules",
        "model_calls": 0,
        "heldout_legit": rail_pass(heldout),
        "golden_questions": rail_pass(golden),
        "attacks_direct": attacks,
    }
    out.write_text(json.dumps(result, indent=1) + "\n")
    for key in ("heldout_legit", "golden_questions", "attacks_direct"):
        part = result[key]
        print(f"{key}: stopped {part['stopped']} of {part['n']}", [w["item"] for w in part["which"]])
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
