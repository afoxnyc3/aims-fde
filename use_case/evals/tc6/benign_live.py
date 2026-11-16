"""Legitimate questions through the shipped answer path on the local model: how many does the app refuse?

    uv run --project 01_Product_Engineering/challenge python use_case/evals/tc6/benign_live.py LABEL [APP_DIR]

APP_DIR defaults to this tree's app. Point it at another commit's app folder (a git worktree) to
get the "before" column from the same questions. Local Ollama only, enforced by local_guard.

Two sets, one pass:
- golden: the 15 questions in ../retrieval.jsonl (3 of them must be declined: that is the right answer).
- larger: one templated question per distinct (role, venue) pair in ../real_v05/golden.jsonl.
  Those labels are for real tickets, so only the template, the pair count and the refused counts
  are written. No ticket ref and no per-question text goes in the output file.
"""

import ast
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LABEL = sys.argv[1]
APP = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / "01_Product_Engineering/challenge"
sys.path[:0] = [str(HERE), str(APP)]
os.environ.setdefault("CORPUS_PATH", str(ROOT / "use_case/data/synthetic_v1.jsonl"))
os.environ.setdefault("EMBED_CACHE_DIR", str(HERE / ".embed_cache"))

import local_guard  # noqa: E402

MODEL, BASE = local_guard.switch_app_to_injection_model()

import qa  # noqa: E402
from qa_schema import QuestionRequest  # noqa: E402

local_guard.assert_app_is_local()

TEMPLATE = "Which system role does a new {role} at {venue} need?"
# Reasons written by code, not the model: each names the gate that withheld the reply.
GATES = {"cited no record": "citation gate", "said access is approved": "output check: approval",
         "link that is not in the standard": "output check: link", "without choosing": "no final call",
         "turn budget": "turn budget"}


def gate(out: dict) -> str | None:
    if not out["declined"]:
        return None
    reason = out["decline_reason"] or ""
    return next((name for needle, name in GATES.items() if needle in reason), "model declined")


def ask(question: str) -> dict:
    started = time.perf_counter()
    try:
        out = qa.answer_question(QuestionRequest(question=question)).model_dump()
    except Exception as exc:
        return {"error": type(exc).__name__, "declined": None, "gate": "error", "latency_s": round(time.perf_counter() - started, 2)}
    return {"declined": out["declined"], "gate": gate(out), "sources": len(out["sources"]),
            "latency_s": round(time.perf_counter() - started, 2)}


def main() -> None:
    golden = [json.loads(line) for line in (HERE.parent / "retrieval.jsonl").read_text().splitlines() if line.strip()]
    pairs = set()
    for line in (HERE.parent / "real_v05/golden.jsonl").read_text().splitlines():
        if line.strip():
            expected = json.loads(line)["expected"]
            expected = ast.literal_eval(expected) if isinstance(expected, str) else expected
            if expected.get("role") and expected.get("venue"):
                pairs.add((expected["role"], expected["venue"]))
    rows = []
    for q in golden:
        rows.append({"set": "golden", "id": q["id"], "must_decline": bool(q.get("must_decline"))} | ask(q["question"]))
        print(rows[-1], flush=True)
    for n, (role, venue) in enumerate(sorted(pairs), 1):
        rows.append({"set": "larger", "id": f"pair-{n:02d}", "must_decline": False} | ask(TEMPLATE.format(role=role, venue=venue)))
        print(rows[-1], flush=True)
    out = HERE / "runs" / f"benign-live-{LABEL}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"label": LABEL, "app_dir": str(APP), "model": MODEL, "template": TEMPLATE,
                               "pairs": len(pairs), "rows": rows}, indent=1), encoding="utf-8")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
