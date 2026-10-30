"""The two tests a judge must pass before its number counts. Costs model calls.

    uv run --project 01_Product_Engineering/challenge python use_case/evals/calibrate_judge.py

Separation: the judge must score known-good above known-bad, on judge_pairs.jsonl,
where each bad answer is its good answer with one unsupported claim added. Those are
harder than echo, which run.py scores.

Agreement: only once human_scores.jsonl exists. Each line with a `grounded` verdict
is compared to the judge, next to the floor you would get by always guessing the
majority answer. calibrate() passing does not check this.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import harness as evals  # noqa: E402


def separation(judge, pairs: list[dict]) -> None:
    good, bad = [], []
    for pair in pairs:
        case = evals.judge_case(pair["question"], [])
        good.append(judge.score(pair["good"], case))
        bad.append(judge.score(pair["bad"], case))
        print(f"  {pair['id']}: good {good[-1]:.0f}, bad {bad[-1]:.0f}  ({pair['breaks']})")
    print(f"separation on {len(pairs)} pairs: good {sum(good) / len(good):.2f}, bad {sum(bad) / len(bad):.2f}")


def agreement(judge, path: Path) -> None:
    lines = [line for line in evals.load_jsonl(path) if line.get("grounded") is not None] if path.exists() else []
    if not lines:
        print("agreement: no `grounded` verdicts yet, so not checked")
        return
    hits = 0
    for line in lines:
        actual = line["actual"] if isinstance(line["actual"], dict) else {}
        said = actual.get("answer") or actual.get("decline_reason") or json.dumps(actual)
        case = evals.judge_case(str(line["input"]), actual.get("sources") or [])
        hits += (judge.score(said, case) >= 0.5) == line["grounded"]
    yes = sum(line["grounded"] for line in lines)
    floor = max(yes, len(lines) - yes) / len(lines)
    print(f"agreement on {len(lines)}: {hits / len(lines):.2f}, chance floor {floor:.2f}")


def main() -> None:
    judge = evals.make_judge()
    print(f"judge {evals.JUDGE_MODEL}: {evals.calibrate(judge)}")
    if not judge.calibration.passed:
        raise SystemExit("Failed separation against an obviously wrong answer. Do not use this judge.")
    separation(judge, evals.load_jsonl(evals.HERE / "judge_pairs.jsonl"))
    agreement(judge, evals.HERE / "human_scores.jsonl")


if __name__ == "__main__":
    main()
