# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "anthropic>=1.15",
#     "deepeval>=4.3",
#     "pydantic>=2",
#     "python-dotenv>=1.0",
# ]
# ///
"""Write synthetic onboarding-ticket text from picks.py rows. The model writes the ticket only.

    uv run use_case/gen/generate.py --role-fit venue_dependent --one-per-cell

Labels come from picks.py and are never shown to the model. Each row is stored as
picks + labels + ticket + provenance in use_case/data/synth_run_<timestamp>.jsonl,
and the schema-valid rows are also saved as a deepeval EvaluationDataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

sys.path.insert(0, str(Path(__file__).parent))
import picks as P  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"

YesNo = Literal["YES", "NO"]


class Fields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    due_date: str
    job_title: str
    location: str
    department: str
    manager_name: str
    user_to_replicate: str


class Form(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manager_email: str
    employee_email: str
    login_required: YesNo
    membership_required: YesNo
    employment_type: str
    rehire: YesNo
    previous_location: str
    specialties: str
    trainer_level: str


class Comment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    author_role: Literal["requester", "service_desk"]
    timestamp: str
    body: str


class Ticket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_type: str
    summary: str
    created: str
    fields: Fields
    form: Form
    notes: str
    comments: list[Comment]


TICKET_SCHEMA = Ticket.model_json_schema()
TOOL = {
    "name": "submit_ticket",
    "description": "Submit the finished service-desk ticket.",
    "strict": True,
    "input_schema": TICKET_SCHEMA,
}

HOUSE_RULES = """Rules for every ticket:
- Use clearly fictional people's names. Every email address ends in @example.com.
- Never use a real company, club, city, or software product name. Clubs are only Club A, Club B, Club C, Club D, Club E. The staff system is called "the club-management system".
- A field you are told to leave blank is an empty string "".
- Write like a busy staff member, not a template. Keep it short and plausible.
- Return the ticket only, by calling the submit_ticket tool once."""

SCOPE_TEXT = {
    "login_from_template": ("YES", "YES"),
    "membership_only": ("NO", "YES"),
    "beyond_template": ("YES", "YES"),
}


def role_description(row: dict) -> str:
    if row["fixed"]:
        return "You are a staff member at a fitness club filing a ticket through the Region A service desk portal."
    return "You are a club manager filing a new-hire onboarding request through the Region A form."


def instructions(row: dict) -> str:
    p = row["picks"]
    if row["fixed"]:
        lines = [
            f"Situation: {row['fixed']['brief']}",
            f'- request_type: exactly "{p["request_type"]}"',
            f'- created: exactly "{p["created"]}"',
            f'- location: {"exactly " + repr(p["club"]) if p["club"] else "blank"}',
            "- Fill only the fields that fit this situation; leave the rest blank. login_required, membership_required and rehire are NO.",
            "- comments: an empty list.",
        ]
        if row["fixed"]["kind"] == "vague_account":
            lines.append("- job_title, location, department and manager_name are blank. The note gives no role, club, or manager.")
        return "\n".join(lines)

    a = row["axes"]
    login, membership = SCOPE_TEXT[a["scope"]]
    blank = p["blank_field"]
    notes = []

    lines = [
        f'- request_type: exactly "{p["request_type"]}"',
        f'- created: exactly "{p["created"]}"',
        f'- job_title: {"blank" if p["title"] is None else "exactly " + json.dumps(p["title"])}',
        f'- department: "{p["department"]}"',
        f'- location: {"blank" if p["club"] is None else "exactly " + json.dumps(p["club"])}',
        f'- due_date (start date): {"blank" if blank == "due_date" else "exactly " + json.dumps(p["due_date"])}',
        "- manager_name and manager_email: a fictional manager.",
    ]
    if blank == "employee_email":
        lines.append("- employee_email: blank")
    elif p["contradiction_variant"] == "b":
        lines.append("- employee_email: exactly the same address as manager_email")
    else:
        lines.append("- employee_email: the new hire's fictional address")
    lines += [
        f"- login_required: {login}",
        f"- membership_required: {membership}",
        "- user_to_replicate: blank",
        "- employment_type: Full-time, Part-time, or Seasonal (your choice)",
        "- specialties and trainer_level: fill only if they fit the job title, and never contradict it; otherwise blank",
    ]

    if a["intent"] == "returning_or_moving":
        lines += ["- rehire: YES", f'- previous_location: exactly "{p["previous_club"]}"']
        word = {"returning": "returning to the company", "transferring": "transferring from another club",
                "promoted": "being promoted into this role"}[p["intent_note"]]
        notes.append(f"say the person is {word}")
    else:
        lines += ["- rehire: NO", "- previous_location: blank"]

    if p["contradiction_variant"] == "a":
        notes.append(f'name {p["contradiction_club"]} as the club the person will work at (the location field still says {p["club"]})')
    if p["extra_request"]:
        notes.append(f'request {p["extra_request"]["text"]} (use those words)')

    if notes:
        lines.append("- notes must: " + "; ".join(notes) + ". Mention no other club.")
    else:
        lines.append("- notes: a short, ordinary note. Mention no club.")

    ch = p["changed"]
    if ch:
        what = {
            "due_date": f'the start date is now {ch["to"]} (write the date exactly as {ch["to"]})',
            "club": f'the person will now work at {ch["to"]} instead of {ch["from"]}',
            "membership": "the person no longer needs a membership",
        }[ch["detail"]]
        lines.append(f'- comments: exactly one comment, author_role "requester", timestamp exactly "{p["comment_ts"]}", saying {what}. Leave the form fields as originally submitted.')
    else:
        lines.append("- comments: an empty list.")
    return "\n".join(lines)


def build_prompt(row: dict) -> tuple[str, str]:
    system = role_description(row)
    user = (
        "Write one service-desk ticket.\n\n"
        f"{instructions(row)}\n\n{HOUSE_RULES}\n\n"
        f"Ticket JSON schema:\n{json.dumps(TICKET_SCHEMA)}"
    )
    return system, user


def render_ticket(t: dict) -> str:
    f, fm = t["fields"], t["form"]
    lines = [f"Request type: {t['request_type']}", f"Summary: {t['summary']}", f"Created: {t['created']}"]
    lines += [f"{k.replace('_', ' ').title()}: {v}" for k, v in f.items()]
    lines += [f"{k.replace('_', ' ').title()}: {v}" for k, v in fm.items()]
    lines.append(f"Notes: {t['notes']}")
    for c in t["comments"]:
        lines.append(f"Comment ({c['author_role']}, {c['timestamp']}): {c['body']}")
    return "\n".join(lines)


class AnthropicBackend:
    def __init__(self, model: str, temperature: float):
        import anthropic

        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.temperature = temperature
        self.send_temperature = True  # dropped after the first 400 that names it

    def call(self, system: str, user: str) -> dict | None:
        kwargs = dict(
            model=self.model, max_tokens=8000, system=system,
            messages=[{"role": "user", "content": user}],
            tools=[TOOL],  # forced tool_choice is a 400 on current models; strict + prompt instead
            output_config={"effort": "low"},
        )
        if self.send_temperature:
            # SDK 1.x dropped the typed parameter; older models still accept it in the body.
            kwargs["extra_body"] = {"temperature": self.temperature}
        try:
            resp = self.client.messages.create(**kwargs)
        except self.anthropic.BadRequestError as e:
            if "temperature" not in str(e) or "extra_body" not in kwargs:
                raise
            if self.send_temperature:  # several workers can hit this at once; note it once
                self.send_temperature = False
                print(f"note: {self.model} rejects temperature; generating without it", file=sys.stderr)
            return self.call(system, user)
        if resp.stop_reason != "tool_use":
            return None
        return next((b.input for b in resp.content if b.type == "tool_use"), None)


class OllamaBackend:
    def __init__(self, model: str, temperature: float):
        self.model = model
        self.temperature = temperature
        self.send_temperature = True
        self.url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/chat"

    def call(self, system: str, user: str) -> dict | None:
        body = json.dumps({
            "model": self.model, "stream": False, "format": TICKET_SCHEMA,
            "options": {"temperature": self.temperature},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            content = json.loads(r.read())["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None


def generate_one(backend, row: dict) -> dict:
    system, user = build_prompt(row)
    out = {"ticket": None, "schema_valid": False, "error": None,
           "prompt_sha": hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()}
    for _attempt in range(2):  # one retry on invalid output, then schema_invalid
        try:
            raw = backend.call(system, user)
        except Exception as e:  # recorded on the row; the run continues
            out["error"] = f"{type(e).__name__}: {e}"
            return out
        if raw is None:
            continue
        try:
            out["ticket"] = Ticket.model_validate(raw).model_dump()
            out["schema_valid"] = True
            return out
        except ValidationError:
            continue
    out["error"] = "schema_invalid"
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    P.add_filter_args(p)
    p.add_argument("--backend", choices=["anthropic", "ollama"], default="anthropic")
    p.add_argument("--model")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()

    os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")

    rows = P.select(P.build_plan(args.seed), args.role_fit, args.one_per_cell, args.limit)
    if args.backend == "anthropic":
        backend = AnthropicBackend(args.model or DEFAULT_ANTHROPIC_MODEL, args.temperature)
    else:
        if not args.model:
            p.error("--model is required with --backend ollama")
        backend = OllamaBackend(args.model, args.temperature)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run = {"timestamp": ts, "role_fit": args.role_fit, "one_per_cell": args.one_per_cell, "limit": args.limit}
    print(f"generating {len(rows)} rows with {args.backend}:{backend.model}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda r: generate_one(backend, r), rows))

    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"synth_run_{ts}.jsonl"
    stored = []
    with out_path.open("w") as fh:
        for row, res in zip(rows, results):
            rec = {**row, **res, "model": backend.model, "backend": args.backend, "seed": args.seed,
                   "temperature": args.temperature if backend.send_temperature else None, "run": run}
            stored.append(rec)
            fh.write(json.dumps(rec) + "\n")

    from deepeval.dataset import EvaluationDataset, Golden

    label_keys = ("row_id", "cell_id", "axes", "fixed", "picks", "expected_status", "role_fit_observable",
                  "expected_proposal", "expected_caveat", "expected_reason", "reference_versions")
    goldens = [Golden(input=render_ticket(r["ticket"]), additional_metadata={k: r[k] for k in label_keys})
               for r in stored if r["schema_valid"]]
    ds_path = EvaluationDataset(goldens=goldens).save_as(
        file_type="json", directory=str(DATA_DIR), file_name=f"synth_run_{ts}_goldens") if goldens else "(no goldens: nothing schema-valid)"

    ok = sum(r["schema_valid"] for r in stored)
    print(f"wrote {out_path} ({ok}/{len(stored)} schema-valid)\nwrote {ds_path}", file=sys.stderr)
    print(out_path)


if __name__ == "__main__":
    main()
