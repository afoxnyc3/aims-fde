"""Re-score saved raw runs in runs/ with the current leak.py scorers. No model calls, no app import.

Rewrites only the four score fields (leaked, leaked_pre_gate, behaviour, behaviour_pre_gate) in
each runs/*.jsonl row; the model output is untouched. Prints per-file counts before and after.
Then rebuild attacks.jsonl with `attack.py summarize`.

    uv run --project 01_Product_Engineering/challenge python use_case/evals/tc6/rescore.py
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parents[2] / "01_Product_Engineering/challenge"
sys.path[:0] = [str(HERE.parent), str(APP)]

import corpus  # noqa: E402  (data loader only; imports no model client)
from leak import behaviour_leaked, leaked  # noqa: E402

FIELDS = ("leaked", "leaked_pre_gate", "behaviour", "behaviour_pre_gate")


def score(row: dict, ref: str) -> dict:
    shipped, pre, question = row.get("qa"), row.get("pre_gate"), row.get("input") or ""
    pre_obj = pre and {"answer": pre.get("answer"), "decline_reason": pre.get("decline_reason"),
                       "trace": {"steps": pre.get("trace", [])}}
    return {"leaked": bool(shipped) and leaked(shipped, question),
            "leaked_pre_gate": bool(pre) and leaked(pre_obj, question),
            "behaviour": bool(shipped) and behaviour_leaked(shipped, ref),
            "behaviour_pre_gate": bool(pre) and behaviour_leaked(pre_obj, ref)}


def main() -> None:
    # Same reference attack.py scored against: the real corpus, never the poisoned overlay.
    ref = "\n".join(page.text for page in corpus.load_corpus(Path(os.getenv("CORPUS_PATH") or corpus.DEFAULT_CORPUS_PATH)))
    for path in sorted((HERE / "runs").glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        before = {f: sum(bool(r[f]) for r in rows) for f in FIELDS}
        for r in rows:
            r.update(score(r, ref))
        after = {f: sum(bool(r[f]) for r in rows) for f in FIELDS}
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        changed = " CHANGED" if before != after else ""
        print(f"{path.name:<58} n={len(rows):<3} " + "  ".join(f"{f} {before[f]}->{after[f]}" for f in FIELDS) + changed)


if __name__ == "__main__":
    main()
