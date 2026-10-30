"""The two tests a judge must pass before its number counts. Costs model calls.

    uv run --project 01_Product_Engineering/challenge python use_case/evals/calibrate_judge.py --repeats 3

Separation: the judge must score known-good above known-bad, on judge_pairs.jsonl,
where each bad answer is its good answer with one unsupported claim added. Those are
harder than echo, which run.py scores. Exits non-zero if either split misses the same
bars as Judge.calibrate.

Agreement: only once human_scores.jsonl exists. Each question line with a `grounded`
verdict is compared to the judge, next to the floor you would get by always guessing
the majority answer. calibrate() passing does not check this.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import harness as evals  # noqa: E402

MIN_GOOD, MAX_BAD = 0.8, 0.3


def separation(judge, pairs: list[dict], repeats: int) -> bool:
    """Per split, because the dev pairs chose the model and the holdout pairs did not."""
    passed = True
    for split in ("dev", "holdout"):
        good, bad = [], []
        for pair in (p for p in pairs if p["split"] == split):
            case = evals.judge_case(pair["question"], [])
            pair_good = [judge.score(pair["good"], case) for _ in range(repeats)]
            pair_bad = [judge.score(pair["bad"], case) for _ in range(repeats)]
            good += pair_good
            bad += pair_bad
            if sum(pair_good) < repeats or sum(pair_bad) > 0:
                print(f"  {pair['id']}: good {pair_good}, bad {pair_bad}  ({pair['breaks']})")
        mean_good, mean_bad = sum(good) / len(good), sum(bad) / len(bad)
        print(f"{split}: good {mean_good:.2f}, bad {mean_bad:.2f}, {len(good)} scores each")
        passed = passed and mean_good > MIN_GOOD and mean_bad < MAX_BAD
    return passed


def agreement(judge, path: Path) -> None:
    lines = evals.load_jsonl(path) if path.exists() else []
    # Tickets are not judged: their access comes from code, so `grounded` does not apply to them.
    lines = [line for line in lines if line.get("grounded") is not None and isinstance(line["input"], str)]
    if not lines:
        print("agreement: no `grounded` verdicts yet, so not checked")
        return
    hits = 0
    for line in lines:
        actual = line["actual"] if isinstance(line["actual"], str) else json.dumps(line["actual"])
        said, sources = evals.what_was_said(actual)
        hits += (judge.score(said, evals.judge_case(line["input"], sources)) >= 0.5) == line["grounded"]
    yes = sum(line["grounded"] for line in lines)
    floor = max(yes, len(lines) - yes) / len(lines)
    print(f"agreement on {len(lines)}: {hits / len(lines):.2f}, chance floor {floor:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repeats", type=int, default=1, help="scores per answer; one run of a judge is a sample of one")
    args = parser.parse_args()

    judge = evals.make_judge()
    print(f"judge {evals.JUDGE_MODEL}: {evals.calibrate(judge)}")
    if not judge.calibration.passed:
        raise SystemExit("Failed separation against an obviously wrong answer. Do not use this judge.")
    passed = separation(judge, evals.load_jsonl(evals.HERE / "judge_pairs.jsonl"), args.repeats)
    agreement(judge, evals.HERE / "human_scores.jsonl")
    if not passed:
        raise SystemExit("Failed separation on the pairs. Do not use this judge.")


if __name__ == "__main__":
    main()
