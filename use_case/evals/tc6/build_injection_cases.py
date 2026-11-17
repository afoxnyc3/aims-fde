"""Turn the saved attack runs into permanent scored cases: runs/*.jsonl -> ../injection_cases.jsonl.

One case per attack. Each keeps the recorded model results that leaked before the app's gates
(`recorded`), so `harness.blocks_injection` can put them back through the shipped answer path with
no model. No model calls here either; nothing is sent anywhere.

    python3 use_case/evals/tc6/build_injection_cases.py

`returned_pages` is what the replay tells the citation gate the run retrieved. The saved runs did
not keep tool outputs, so it is set to the worst case for the gate: a run that made no tool call
returned nothing (certain); a run that made one is assumed to have returned every page it cites.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
OUT = HERE.parent / "injection_cases.jsonl"
PASS = "20261115-235"  # the re-run the README tables come from
PAGE_ID = re.compile(r"\b(?:SYN-[0-9a-f]{6}|STD-[a-z]+(?:-[a-z]+)*)\b")
KEEP = ("answer", "trace", "calls", "evidence_chars", "tokens", "latency_s", "stopped", "decline_reason", "retried")


def main() -> None:
    cases: dict[tuple, dict] = {}
    for path in sorted(RUNS.glob(f"*_{PASS}*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            run = json.loads(line)
            key = (run["door"], run["kind"], run["input"])
            case = cases.setdefault(key, {
                "id": f"INJ-{len(cases) + 1:02d}", "kind": "injection", "door": run["door"], "attack": run["kind"],
                "input": run["input"], "context": run.get("context"), "runs": 0, "shipped_before_fix": 0,
                "leaked_pre_gate": 0, "recorded": [], "pages": [], "source_runs": []})
            case["runs"] += 1
            case["shipped_before_fix"] += int(bool(run["leaked"] or run["behaviour"]))
            if path.name not in case["source_runs"]:
                case["source_runs"].append(path.name)
            if not (run["leaked_pre_gate"] or run["behaviour_pre_gate"]):
                continue
            case["leaked_pre_gate"] += 1
            pre = run["pre_gate"]
            said = (pre.get("answer") or "") + " " + (pre.get("decline_reason") or "")
            cited = list(dict.fromkeys(PAGE_ID.findall(said)))
            recorded = {k: pre.get(k) for k in KEEP} | {"returned_pages": cited if pre.get("calls") else []}
            case["recorded"].append(recorded)
            poisoned = (run.get("context") or {}).get("poisoned_page")
            for name in cited:
                if name.startswith("SYN-") and name not in [p["name"] for p in case["pages"]]:
                    injected = (run["context"] or {}).get("injection", "") if name == poisoned else ""
                    # A stand-in for the ticket: the data file is private to the machine. The poisoned
                    # one carries its injection; its status field is what poison.py gave the row.
                    case["pages"].append({"name": name, "title": "stand-in ticket", "text": f"# {name}\n{injected}",
                                          "status": "human_review" if name == poisoned else "recommended"})
    OUT.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases.values()), encoding="utf-8")
    for c in cases.values():
        print(f"{c['id']} {c['door']:<16} {c['attack']:<26} runs {c['runs']:>2} shipped {c['shipped_before_fix']} "
              f"pre-gate {c['leaked_pre_gate']} recorded {len(c['recorded'])}")
    print(f"wrote {OUT} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
