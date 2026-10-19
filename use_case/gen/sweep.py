# /// script
# requires-python = ">=3.12"
# dependencies = ["litellm>=1.90", "pydantic>=2"]
# ///
"""Local open-weight sweep: one model x 9 (temperature, top_p) settings x 24 rows.

Usage:
  uv run use_case/gen/sweep.py --model ollama_chat/qwen3:4b --settings base   # trial: 1 setting
  uv run use_case/gen/sweep.py --model ollama_chat/qwen3:4b                   # full 9 x 24
  uv run use_case/gen/sweep.py --report use_case/data/sweep_<...>.jsonl

Resume: the default output name is timestamped, so a plain rerun starts a new file.
After a crash or Ctrl-C, rerun with --out <the existing .jsonl> to skip rows already done.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic import ValidationError

from helpers import llm, nb
from generate import Ticket, build_prompt
from picks import build_plan
from verify import check

FIXED = {"top_k": 0, "repeat_penalty": 1.0, "num_ctx": 8192}   # Ollama "options"
THINK = False                                                   # Ollama top-level
GRID = [(t, p) for t in (0.2, 0.7, 1.0) for p in (0.5, 0.8, 0.95)]  # T=1.0 provisional (Session 3)
BASE = [(0.7, 0.8)]
DIGESTS = {"ollama_chat/qwen3:4b": "359d7dd4bcda", "ollama_chat/qwen3:8b": "500a1f067a9f"}
TOP_K_NOTE = ("disabled; runner is llama.cpp per `ollama ps`, top_k<=0 means no limit; "
              "LiteLLM forwarding to options verified")
SCHEMA = Ticket.model_json_schema()
SCHEMA_SHA = hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode()).hexdigest()[:12]


# ---------- server address (one source for digest check and calls) ----------
def ollama_url(cfg) -> str:
    return getattr(cfg, "api_base", None) or os.environ.get("LOCAL_MODEL_BASE_URL", "http://localhost:11434")


# ---------- model call ----------
def call_model(cfg, system: str, user: str, *, model: str, url: str, temperature: float, top_p: float,
               seed: int) -> tuple[dict | None, str]:
    """Exceptions propagate; llm.complete already retries timeouts and 5xx."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    resp = llm.complete(
        cfg, messages, model=model, api_base=url,
        temperature=temperature, top_p=top_p, seed=seed, **FIXED, think=THINK,
        response_format={"type": "json_schema", "json_schema": {"name": "Ticket", "schema": SCHEMA}},
    )
    text = resp.choices[0].message.content or ""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None, text
    return (obj if isinstance(obj, dict) else None), text


def seed_for(row_id: str) -> int:
    """Same seed per row across all settings and models: differences come from settings."""
    return int(hashlib.sha256(row_id.encode()).hexdigest()[:8], 16)


def prompt_sha(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n" + user).encode()).hexdigest()[:12]


# ---------- selection ----------
def select_slice(plan) -> list[dict]:
    """venue_dependent + outside_standard, new_hire, first row per cell -> 24.
    First-per-cell = row #0 of each cell in build_plan's fixed cross-product order."""
    keep = [r for r in plan
            if r["axes"]                                   # fixed rows have axes=None
            and r["axes"]["role_fit"] in ("venue_dependent", "outside_standard")
            and r["axes"]["intent"] == "new_hire"]
    seen, out = set(), []
    for r in keep:
        if r["cell_id"] not in seen:
            seen.add(r["cell_id"])
            out.append(r)
    assert len(out) == 24, len(out)
    return out


# ---------- one row (shared by check and sweep) ----------
def generate_local(cfg, row: dict, *, model: str, url: str, temperature: float, top_p: float) -> dict:
    system, user = build_prompt(row)
    seed = seed_for(row["row_id"])
    t0 = time.monotonic()
    obj, raw = call_model(cfg, system, user, model=model, url=url,
                          temperature=temperature, top_p=top_p, seed=seed)
    rec = {
        "row_id": row["row_id"], "cell_id": row["cell_id"],
        "model": model, "model_digest": DIGESTS[model], "ollama_url": url,
        "temperature": temperature, "top_p": top_p, "seed": seed, **FIXED, "think": THINK,
        "top_k_note": TOP_K_NOTE,
        "prompt_sha": prompt_sha(system, user), "schema_sha": SCHEMA_SHA,
        "latency_s": round(time.monotonic() - t0, 2),
        "raw_reply": raw,
        "axes": row["axes"], "picks": row["picks"], "expected_status": row["expected_status"],
    }
    rec.update(classify(row, obj, user))
    return rec


def classify(row: dict, obj: dict | None, user: str) -> dict:
    """Everything after the model call: outcome, schema errors, verification, echo. No model needed."""
    if obj is None:
        return {"outcome": "unparseable"}
    try:
        Ticket.model_validate(obj)
    except ValidationError as e:
        return {"outcome": "schema_invalid", "schema_errors": json.loads(e.json(include_url=False))}
    fails, matches = check({**row, "ticket": obj})
    grams = echo_ngrams(row, obj, user)
    return {"outcome": "schema_valid", "ticket": obj, "verified": not fails, "verify_failures": fails,
            "verify_matches": matches, "echo_ngrams": grams, "echo": bool(grams)}


# ---------- echo: prompt wording copied into the ticket ----------
# Phrases the prompt tells the model to use (mirrors generate.instructions()). Copying them is
# following the instruction, not echo: the system name, the intent note, and what a change
# comment or contradiction-a note must say.
MANDATED = ["club-management system", "returning to the company", "transferring from another club",
            "being promoted into this role", "the start date is now", "will now work at", "instead of",
            "will work at", "no longer needs a membership"]
STOPWORDS = set("""a an the and or but if of to in on at for from by with as is are was were be been being
it its this that these those he she they them his her their our we you your i me my no not do does did
will would can could should has have had so than then there here also just please""".split())


# Pick fields that are labels, not values written into the ticket ("club", "returning", "a", ...).
# Masking them would hide ordinary words: changed.detail == "club" masked every "club".
LABEL_KEYS = {"detail", "kind", "keywords", "blank_field", "contradiction_variant",
              "near_match_variant", "intent_note"}


def _pick_values(x):
    if isinstance(x, dict):
        for k, v in x.items():
            if k not in LABEL_KEYS:
                yield from _pick_values(v)
    elif isinstance(x, list):
        for v in x:
            yield from _pick_values(v)
    elif isinstance(x, str) and len(x) > 2:
        yield x


def _tokens(text: str, masks: list[str]) -> list[str]:
    text = EMAIL.sub(" <p> ", text.lower())
    for m in masks:                                    # longest first, so "Club D" beats "Club"
        text = text.replace(m, " <p> ")
    text = DATE.sub(" <p> ", text)
    words = re.sub(r"[^\w<>\s]", " ", text).split()
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words]   # crude plural fold


def _grams(tokens: list[str]) -> set[tuple[str, ...]]:
    return {g for g in zip(tokens, tokens[1:], tokens[2:])
            if "<p>" not in g and not all(w in STOPWORDS for w in g)}


def echo_ngrams(row: dict, ticket: dict, user: str) -> list[str]:
    """Word 3-grams in both the prompt's instructions and the ticket's notes + comments.
    Code-picked values and mandated phrases are masked first, so copying them never counts."""
    instructions = user.split("Ticket JSON schema:")[0]
    masks = sorted({v.lower() for v in _pick_values(row["picks"])} | set(MANDATED), key=len, reverse=True)
    written = " ".join([ticket.get("notes") or ""] + [c.get("body") or "" for c in ticket.get("comments") or []])
    return sorted(" ".join(g) for g in _grams(_tokens(written, masks)) & _grams(_tokens(instructions, masks)))


# ---------- run bookkeeping ----------
def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def check_digest(model: str, url: str) -> None:
    name = model.split("/", 1)[1]
    with urllib.request.urlopen(f"{url}/api/tags", timeout=10) as r:
        tags = json.load(r)["models"]
    found = {m["name"]: m["digest"] for m in tags}
    digest = found.get(name) or found.get(f"{name}:latest")
    if not digest or not digest.startswith(DIGESTS[model]):
        sys.exit(f"Digest mismatch for {name} at {url}: expected {DIGESTS[model]}, found {digest}")


def warm_up(cfg, model: str, url: str) -> float:
    t0 = time.monotonic()
    llm.complete(cfg, [{"role": "user", "content": "Reply with OK."}], model=model, api_base=url,
                 temperature=0.0, top_p=1.0, seed=0, **FIXED, think=THINK)
    return round(time.monotonic() - t0, 2)


def load_done_keys(path: Path) -> set:
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text().splitlines():
        r = json.loads(line)
        keys.add((r["model"], r["temperature"], r["top_p"], r["row_id"], r["prompt_sha"]))
    return keys


def append_jsonl(path: Path, rec: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2))


# ---------- sweep ----------
def sweep(model: str, settings: list[tuple[float, float]], out_path: Path, resume: bool = True) -> None:
    cfg = nb.bootstrap(start=Path(__file__))
    url = ollama_url(cfg)
    check_digest(model, url)
    rows = select_slice(build_plan())
    done = load_done_keys(out_path) if resume else set()
    manifest_path = out_path.with_suffix(".manifest.json")
    manifest = {
        "run_id": out_path.stem, "model": model, "model_digest": DIGESTS[model], "ollama_url": url,
        "grid": settings, "fixed": FIXED, "think": THINK, "top_k_note": TOP_K_NOTE,
        "schema_sha": SCHEMA_SHA, "git_sha": git_sha(), "n_rows": len(rows),
        "started": datetime.now(timezone.utc).isoformat(), "status": "running",
    }
    manifest["warmup_s"] = warm_up(cfg, model, url)
    write_manifest(manifest_path, manifest)
    key, written = None, 0
    try:
        for t, p in settings:
            for row in rows:
                system, user = build_prompt(row)
                key = (model, t, p, row["row_id"], prompt_sha(system, user))
                if key in done:
                    continue
                rec = generate_local(cfg, row, model=model, url=url, temperature=t, top_p=p)
                rec["run_id"] = manifest["run_id"]
                append_jsonl(out_path, rec)
                written += 1
        manifest["status"] = "complete"
    except BaseException as exc:                      # includes KeyboardInterrupt
        manifest.update(status="aborted", aborted_at=list(key) if key else None, error=repr(exc))
        raise
    finally:
        manifest.update(finished=datetime.now(timezone.utc).isoformat(), rows_written=written)
        write_manifest(manifest_path, manifest)


# ---------- report: Step 2 counts per setting ----------
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z?)?|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")


def _strings(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str) and len(x) > 2:
        yield x


def masked_text(rec: dict) -> str:
    """Variable content only, with code-picked values masked (the decisions.md rule)."""
    t = rec["ticket"]
    text = " ".join([t.get("summary") or "", t.get("notes") or ""] +
                    [(c.get("body") or "") for c in (t.get("comments") or [])])
    for v in sorted(set(_strings(rec["picks"])), key=len, reverse=True):
        text = text.replace(v, "<PICK>")
    return DATE.sub("<DATE>", EMAIL.sub("<EMAIL>", text)).lower()


def jaccard5(a: str, b: str) -> float:
    A = {a[i:i + 5] for i in range(len(a) - 4)}
    B = {b[i:i + 5] for i in range(len(b) - 4)}
    return len(A & B) / len(A | B) if A | B else 0.0


def report(path: Path, threshold: float = 0.85) -> None:
    recs = [json.loads(l) for l in path.read_text().splitlines()]
    groups = defaultdict(list)
    for r in recs:
        groups[(r["model"], r["temperature"], r["top_p"])].append(r)

    print(f"{'model':12} {'T':>4} {'p':>5} {'gen':>4} {'unpars':>6} {'sch_inv':>7} {'valid':>5} "
          f"{'verif':>5} {'dedup':>5} {'dead':>4} {'echo':>4} {'xcell_max':>9} {'xcell>=thr':>10}  fail_types")
    for k in sorted(groups):
        rs = groups[k]
        gen = sum(1 for r in rs if r["raw_reply"])
        c = Counter(r["outcome"] for r in rs)
        valid = [r for r in rs if r["outcome"] == "schema_valid"]
        verified = [r for r in valid if r["verified"]]
        cells = {r["cell_id"] for r in rs}
        dead = len(cells - {r["cell_id"] for r in verified})
        ft = Counter(f["pick_type"] for r in valid for f in r["verify_failures"])
        texts = [(r["cell_id"], masked_text(r)) for r in valid]
        sims = [jaccard5(a, b) for i, (ca, a) in enumerate(texts)
                for cb, b in texts[i + 1:] if ca != cb]
        xmax = max(sims, default=0.0)
        xhit = sum(s >= threshold for s in sims)
        echo = sum(1 for r in valid if r.get("echo"))
        print(f"{k[0].split('/')[-1]:12} {k[1]:>4} {k[2]:>5} {gen:>4} {c['unparseable']:>6} "
              f"{c['schema_invalid']:>7} {c['schema_valid']:>5} {len(verified):>5} {len(verified):>5} "
              f"{dead:>4} {echo:>4} {xmax:>9.2f} {xhit:>10}  {dict(ft) or ''}")
    top = Counter(g for r in recs for g in r.get("echo_ngrams") or []).most_common(3)
    print("\nmost common echoed 3-grams:", ", ".join(f"'{g}' x{n}" for g, n in top) or "none")
    print("dedup = verified by construction: one row per cell per setting, and same-cell dedupe "
          "cannot drop anything. Cross-cell pairs >= threshold are reported, not merged.")


def selftest() -> None:
    """Exercise the failure paths of classify() without a model call."""
    row = select_slice(build_plan())[0]
    _, user = build_prompt(row)
    bad_json = classify(row, None, user)               # what call_model returns for non-JSON text
    assert bad_json["outcome"] == "unparseable", bad_json
    missing = {"request_type": "New Hire Onboarding"}  # required Ticket fields absent
    invalid = classify(row, missing, user)
    assert invalid["outcome"] == "schema_invalid", invalid
    assert invalid["schema_errors"], invalid
    for rec in (bad_json, invalid):
        json.dumps(rec)                                # schema_errors must be JSON-safe
    print(f"selftest ok: unparseable, schema_invalid ({len(invalid['schema_errors'])} errors), both serialize")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(DIGESTS))
    ap.add_argument("--settings", choices=["base", "grid"], default="grid")
    ap.add_argument("--out", type=Path, help="existing .jsonl to resume into")
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--report", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        sys.exit()
    if a.report:
        report(a.report)
        sys.exit()
    if not a.model:
        ap.error("--model is required unless --report is given")
    out = a.out or REPO_ROOT / "use_case/data" / (
        f"sweep_{a.model.split('/')[-1].replace(':', '-')}_{a.settings}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
    print(out)
    sweep(a.model, BASE if a.settings == "base" else GRID, out, resume=not a.no_resume)
