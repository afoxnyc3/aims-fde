"""Print counts for a verified synthetic run.

    python use_case/gen/report.py use_case/data/synth_run_<timestamp>.jsonl

Dedupe follows use_case/decisions.md (TC2 Step 2, provisional): character 5-gram
Jaccard over variable content only, pairs at or above the threshold dropped
within the same cell_id, cross-cell pairs reported but not merged. It is skipped
for --one-per-cell runs, where no cell has a second row to drop.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from itertools import combinations
from pathlib import Path


def variable_text(t: dict) -> str:
    parts = list(t["fields"].values()) + list(t["form"].values()) + [t["notes"]]
    parts += [c["body"] for c in t["comments"]]
    return " ".join(str(v) for v in parts).lower()


def shingles(s: str, n: int = 5) -> set[str]:
    return {s[i:i + n] for i in range(max(len(s) - n + 1, 1))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_file", type=Path)
    ap.add_argument("--threshold", type=float, default=0.85)
    args = ap.parse_args()

    rows = [json.loads(line) for line in args.run_file.read_text().splitlines() if line.strip()]
    if any("verified" not in r for r in rows):
        raise SystemExit("run verify.py on this file first")

    cells = Counter(r["cell_id"] for r in rows)
    verified_cells = Counter(r["cell_id"] for r in rows if r["verified"])
    dead = sorted(c for c in cells if verified_cells[c] == 0)
    by_pick = Counter()
    for r in rows:
        for pt in {f["pick_type"] for f in r.get("verify_failures", [])}:
            by_pick[pt] += 1

    print(f"run:            {args.run_file.name}")
    print(f"planned:        {len(rows)} rows in {len(cells)} cells")
    print(f"generated:      {sum(r['ticket'] is not None for r in rows)}")
    print(f"schema-valid:   {sum(r['schema_valid'] for r in rows)}")
    print(f"verified:       {sum(r['verified'] for r in rows)}")
    print(f"dead cells:     {len(dead)}")
    for c in dead:
        print(f"  - {c}")
    print("verification failures by pick type (rows):")
    for pt, n in by_pick.most_common() or [("none", 0)]:
        print(f"  {pt:<15} {n}")

    if rows[0].get("run", {}).get("one_per_cell"):
        print("dedupe:         skipped (--one-per-cell run)")
        return

    valid = [r for r in rows if r["schema_valid"]]
    sh = {r["row_id"]: shingles(variable_text(r["ticket"])) for r in valid}
    dropped, cross = set(), []
    for x, y in combinations(valid, 2):
        score = jaccard(sh[x["row_id"]], sh[y["row_id"]])
        if score < args.threshold:
            continue
        if x["cell_id"] == y["cell_id"]:
            dropped.add(y["row_id"])
        else:
            cross.append((x["row_id"], y["row_id"], score))
    print(f"dedupe @ {args.threshold}: {len(dropped)} same-cell rows dropped, {len(cross)} cross-cell pairs reported")
    for rid in sorted(dropped):
        print(f"  dropped {rid}")
    for a, b, s in sorted(cross, key=lambda c: -c[2])[:20]:
        print(f"  cross   {s:.2f}  {a}  ~  {b}")


if __name__ == "__main__":
    main()
