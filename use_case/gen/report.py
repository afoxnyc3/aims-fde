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


# Picks that legitimately vary between rows of one cell without changing what is
# tested. A dropped pair differing in any OTHER pick means the threshold is too low.
INCIDENTAL = {"created", "due_date", "comment_ts", "requester_name", "requester_email",
              "manager_name", "manager_email", "employee_name", "employee_email"}


def differing_picks(x: dict, y: dict) -> list[str]:
    px, py = x["picks"], y["picks"]
    return sorted(k for k in px.keys() | py.keys() if px.get(k) != py.get(k))


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

    verified = [r for r in rows if r["verified"]]
    sh = {r["row_id"]: shingles(variable_text(r["ticket"])) for r in verified}
    dropped, pairs, cross = set(), [], []
    for x, y in combinations(verified, 2):
        score = jaccard(sh[x["row_id"]], sh[y["row_id"]])
        if score < args.threshold:
            continue
        if x["cell_id"] == y["cell_id"]:
            if y["row_id"] not in dropped:
                dropped.add(y["row_id"])
                pairs.append((x, y, score))
        else:
            cross.append((x["row_id"], y["row_id"], score))
    print(f"after dedupe:   {len(verified) - len(dropped)} (verified, minus {len(dropped)} same-cell rows dropped at Jaccard >= {args.threshold})")
    print("dropped pairs (same cell):")
    if not pairs:
        print("  none")
    for x, y, score in pairs:
        diff = differing_picks(x, y)
        substantive = [k for k in diff if k not in INCIDENTAL]
        print(f"  {score:.2f}  kept {x['row_id']}  dropped {y['row_id']}")
        print(f"        picks differ: {', '.join(substantive) or 'none'}"
              f"  (incidental: {', '.join(k for k in diff if k in INCIDENTAL) or 'none'})")
    print(f"cross-cell pairs >= {args.threshold} (reported, not merged): {len(cross)}")
    for a, b, s in sorted(cross, key=lambda c: -c[2])[:20]:
        print(f"  {s:.2f}  {a}  ~  {b}")
    # Highest same-cell similarity actually observed, for threshold calibration.
    same = [jaccard(sh[x["row_id"]], sh[y["row_id"]]) for x, y in combinations(verified, 2) if x["cell_id"] == y["cell_id"]]
    if same:
        print(f"same-cell Jaccard: max {max(same):.2f}, mean {sum(same) / len(same):.2f} over {len(same)} pairs")


if __name__ == "__main__":
    main()
