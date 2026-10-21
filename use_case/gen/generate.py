# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "anthropic>=1.15",
#     "pydantic>=2",
#     "python-dotenv>=1.0",
# ]
# ///
"""Write synthetic onboarding-ticket text from picks.py rows. The model writes the ticket only.

    uv run use_case/gen/generate.py --role-fit venue_dependent --one-per-cell

Labels come from picks.py and are never shown to the model. Each row is stored as
picks + labels + ticket + provenance in use_case/data/synth_run_<timestamp>.jsonl.
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
- Use the people's names and email addresses exactly as given. If the situation needs anyone else, invent a clearly fictional name. Every email address ends in @example.com.
- Never use a real company, club, city, or software product name. Clubs are only Club A, Club B, Club C, Club D, Club E. The staff system is called "the club-management system".
- A field you are told to leave blank is an empty string "".
- Write like a busy staff member, not a template. Keep it short and plausible.
- Return the ticket only, by calling the submit_ticket tool once."""

SCOPE_TEXT = {
    "member_plus_staff_login": ("YES", "YES"),
    "member_record_only": ("NO", "YES"),
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
            f'- The ticket is filed by {p["requester_name"]} ({p["requester_email"]}). End the notes with "- {p["requester_name"]}".',
        ]
        if p.get("employee_name"):
            lines.append(f'- The employee this is about is {p["employee_name"]} ({p["employee_email"]}). Use that name.')
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
        f'- manager_name: exactly "{p["manager_name"]}"; manager_email: exactly "{p["manager_email"]}"',
        f'- The new hire is {p["employee_name"]}. Refer to them by this name in the summary or notes.',
    ]
    if blank == "employee_email":
        lines.append("- employee_email: blank")
    elif p["contradiction_variant"] == "b":
        lines.append(f'- employee_email: exactly "{p["manager_email"]}" (the same as manager_email)')
    else:
        lines.append(f'- employee_email: exactly "{p["employee_email"]}"')
    lines += [
        "- This request covers two jobs: (1) a member record in the club-management system, which every employee gets, and (2) a staff login with a role, which depends on the role.",
        f"- membership_required (the member record): {membership}",
        f"- login_required (the staff login): {login}",
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
    lines.append(f'- The ticket is filed by {p["requester_name"]}. End the notes with "- {p["requester_name"]}". Mention no people other than those named in these instructions.')
    if p["contradiction_variant"]:
        lines.append("- Do not explain, justify, or acknowledge the inconsistency.")

    ch = p["changed"]
    if ch:
        what = {
            "due_date": f'the start date is now {ch["to"]} (write the date exactly as {ch["to"]})',
            "club": f'the person will now work at {ch["to"]} instead of {ch["from"]}',
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


class AnthropicBackend:
    def __init__(self, model: str, temperature: float):
        import anthropic

        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.temperature = temperature
        self.send_temperature = temperature is not None  # dropped after the first 400 that names it

    def call(self, system: str, user: str) -> tuple[dict | None, object]:
        """Returns (tool input or None, what the model actually returned)."""
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
        details = getattr(resp, "stop_details", None)
        raw = {"stop_reason": resp.stop_reason,
               "stop_details": details.model_dump() if details is not None else None, "content": [
            {"type": b.type, **({"text": b.text} if b.type == "text" else {}),
             **({"input": b.input} if b.type == "tool_use" else {})}
            for b in resp.content]}
        if resp.stop_reason != "tool_use":
            return None, raw
        return next((b.input for b in resp.content if b.type == "tool_use"), None), raw


class OllamaBackend:
    def __init__(self, model: str, temperature: float):
        self.model = model
        self.temperature = temperature
        self.send_temperature = True
        self.url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/chat"

    def call(self, system: str, user: str) -> tuple[dict | None, object]:
        """Returns (parsed JSON or None, the raw reply text)."""
        body = json.dumps({
            "model": self.model, "stream": False, "format": TICKET_SCHEMA,
            "options": {"temperature": self.temperature},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            content = json.loads(r.read())["message"]["content"]
        try:
            return json.loads(content), content
        except json.JSONDecodeError:
            return None, content


def generate_one(backend, row: dict) -> dict:
    system, user = build_prompt(row)
    out = {"ticket": None, "schema_valid": False, "error": None, "failed_attempts": [],
           "prompt_sha": hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()}
    for attempt in range(2):  # one retry on invalid output, then schema_invalid
        try:
            parsed, raw = backend.call(system, user)
        except Exception as e:  # recorded on the row; the run continues
            out["error"] = f"{type(e).__name__}: {e}"
            return out
        if parsed is None:
            # Keep what came back, so a dead cell has a cause and not just a count.
            out["failed_attempts"].append({"attempt": attempt, "why": "no_parseable_output", "raw": raw})
            continue
        try:
            out["ticket"] = Ticket.model_validate(parsed).model_dump()
            out["schema_valid"] = True
            return out
        except ValidationError as e:
            out["failed_attempts"].append({"attempt": attempt, "why": "pydantic", "raw": raw,
                                           "validation_errors": e.errors(include_url=False, include_input=False, include_context=False)})
            continue
    out["error"] = "schema_invalid"
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    P.add_filter_args(p)
    p.add_argument("--backend", choices=["anthropic", "ollama"], default="anthropic")
    p.add_argument("--model")
    p.add_argument("--temperature", type=float, default=None,
                   help="Ollama defaults to 0.7; Anthropic sends nothing unless given (current models reject it)")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")

    rows = P.select(P.build_plan(args.seed), args.role_fit, args.one_per_cell, args.limit, args.fixed_only)
    if args.backend == "anthropic":
        backend = AnthropicBackend(args.model or DEFAULT_ANTHROPIC_MODEL, args.temperature)
    else:
        if not args.model:
            p.error("--model is required with --backend ollama")
        backend = OllamaBackend(args.model, 0.7 if args.temperature is None else args.temperature)

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
                   "temperature": backend.temperature if backend.send_temperature else None, "run": run}
            stored.append(rec)
            fh.write(json.dumps(rec) + "\n")

    ok = sum(r["schema_valid"] for r in stored)
    print(f"wrote {out_path} ({ok}/{len(stored)} schema-valid)", file=sys.stderr)
    print(out_path)


if __name__ == "__main__":
    main()
