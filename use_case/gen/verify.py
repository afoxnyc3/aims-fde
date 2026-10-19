"""Check each generated ticket contains its picks. Rewrites the run file in place.

    python use_case/gen/verify.py use_case/data/synth_run_<timestamp>.jsonl

Adds `verified` and `verify_failures` ([{pick_type, detail}]) to every row. A row
that fails stays in the file with verified=false. Labels are never touched: a
failure is a generation failure, not a reason to relabel.

Verification proves a ticket CONTAINS its picks, not that it is plausible.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

SCOPE_FORM = {
    "login_from_template": ("YES", "YES"),
    "membership_only": ("NO", "YES"),
    "beyond_template": ("YES", "YES"),
}
# Accepted phrases for the Axis 2 note, checked case-insensitively in this order.
# The first match is recorded on the row as verify_matches.intent_note.
INTENT_PHRASES = {
    "returning": ["returning", "coming back", "rejoining", "back with us", "back on the team"],
    "transferring": ["transferring", "transfer", "moving over from", "moving from"],
    "promoted": ["promoted", "promotion"],
}
NEGATION = re.compile(r"\b(no|not|n't|don't|doesn't|without|cancel\w*|remove\w*|drop\w*)\b", re.I)


def _ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.strip().replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def check(row: dict) -> tuple[list[dict], dict]:
    t, p = row["ticket"], row["picks"]
    fails: list[dict] = []
    matches: dict = {}

    def fail(pick_type: str, detail: str) -> None:
        fails.append({"pick_type": pick_type, "detail": detail})

    f, fm, notes = t["fields"], t["form"], t["notes"]

    if t["request_type"].strip() != p["request_type"]:
        fail("request_type", f"{t['request_type']!r} != {p['request_type']!r}")
    if _ts(t["created"]) != _ts(p["created"]):
        fail("created", f"{t['created']!r} != {p['created']!r}")
    emails = [e for e in (fm["manager_email"], fm["employee_email"]) if e]
    if any(not e.strip().lower().endswith("@example.com") for e in emails):
        fail("fictional", f"non-example.com email in {emails}")
    if p["requester_name"] not in notes:
        fail("names", f"requester {p['requester_name']!r} not in notes")

    if row["fixed"]:
        if p["club"] and p["club"] not in f["location"]:
            fail("club", f"{p['club']} not in location {f['location']!r}")
        if row["fixed"]["kind"] == "vague_account":
            filled = [k for k in ("job_title", "location", "department", "manager_name") if f[k].strip()]
            if filled:
                fail("blank_field", f"vague request has {filled} filled")
        if p.get("employee_name") and p["employee_name"].split()[0] not in t["summary"] + " " + notes:
            fail("names", f"employee {p['employee_name']!r} not named in summary or notes")
        return fails, matches

    a = row["axes"]

    # Names: code-picked; the model must use them as given.
    if f["manager_name"].strip() != p["manager_name"]:
        fail("names", f"manager_name {f['manager_name']!r} != {p['manager_name']!r}")
    if fm["manager_email"].strip().lower() != p["manager_email"]:
        fail("names", f"manager_email {fm['manager_email']!r} != {p['manager_email']!r}")
    if p["blank_field"] != "employee_email" and p["contradiction_variant"] != "b" \
            and fm["employee_email"].strip().lower() != p["employee_email"]:
        fail("names", f"employee_email {fm['employee_email']!r} != {p['employee_email']!r}")
    first = p["employee_name"].split()[0]
    if first not in t["summary"] + " " + notes:
        fail("names", f"employee {p['employee_name']!r} not named in summary or notes")

    # Axis 1: title and club.
    if p["title"] is None:
        if f["job_title"].strip():
            fail("blank_field", f"job_title should be blank, got {f['job_title']!r}")
    elif f["job_title"].strip() != p["title"]:
        fail("title", f"{f['job_title']!r} != {p['title']!r}")
    if p["club"] is None:
        if f["location"].strip():
            fail("blank_field", f"location should be blank, got {f['location']!r}")
    elif p["club"] not in f["location"]:
        fail("club", f"{p['club']} not in location {f['location']!r}")

    # Axis 3.
    blank = p["blank_field"]
    if blank == "due_date" and f["due_date"].strip():
        fail("blank_field", f"due_date should be blank, got {f['due_date']!r}")
    elif blank == "employee_email" and fm["employee_email"].strip():
        fail("blank_field", f"employee_email should be blank, got {fm['employee_email']!r}")
    if blank != "due_date" and f["due_date"].strip() != p["due_date"]:
        fail("due_date", f"{f['due_date']!r} != {p['due_date']!r}")

    if p["contradiction_variant"] == "a" and p["contradiction_club"] not in notes:
        fail("contradiction", f"{p['contradiction_club']} not named in notes")
    if p["contradiction_variant"] == "b":
        if not fm["manager_email"].strip() or fm["manager_email"].strip().lower() != fm["employee_email"].strip().lower():
            fail("contradiction", f"emails differ: {fm['manager_email']!r} vs {fm['employee_email']!r}")

    ch = p["changed"]
    if ch:
        created = _ts(t["created"])
        req = [c for c in t["comments"] if c["author_role"] == "requester"]
        later = [c for c in req if created and _ts(c["timestamp"]) and _ts(c["timestamp"]) > created]
        if not later:
            fail("changed", "no requester comment timestamped after created")
        else:
            body = " ".join(c["body"] for c in later)
            if ch["detail"] in ("due_date", "club") and ch["to"] not in body:
                fail("changed", f"comment does not state new {ch['detail']} {ch['to']!r}")
            if ch["detail"] == "membership" and not ("membership" in body.lower() and NEGATION.search(body)):
                fail("changed", "comment does not drop the membership")
    elif t["comments"]:
        fail("changed", f"{len(t['comments'])} unexpected comment(s)")

    # Axis 2.
    if a["intent"] == "returning_or_moving":
        if fm["rehire"] != "YES":
            fail("intent", "rehire is not YES")
        if p["previous_club"] not in fm["previous_location"]:
            fail("intent", f"previous_location {fm['previous_location']!r} lacks {p['previous_club']}")
        hit = next((ph for ph in INTENT_PHRASES[p["intent_note"]] if ph in notes.lower()), None)
        matches["intent_note"] = hit
        if hit is None:
            fail("intent", f"notes do not say {p['intent_note']} (no accepted phrase)")
    else:
        if fm["rehire"] != "NO":
            fail("intent", "rehire is not NO")
        if fm["previous_location"].strip():
            fail("intent", f"previous_location should be blank, got {fm['previous_location']!r}")

    # Axis 4.
    login, membership = SCOPE_FORM[a["scope"]]
    if (fm["login_required"], fm["membership_required"]) != (login, membership):
        fail("scope", f"login/membership {fm['login_required']}/{fm['membership_required']} != {login}/{membership}")
    if p["extra_request"]:
        missing = [k for k in p["extra_request"]["keywords"] if k.lower() not in notes.lower()]
        if missing:
            fail("extra_request", f"notes lack {missing}")

    return fails, matches


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_file", type=Path)
    args = ap.parse_args()

    rows = [json.loads(line) for line in args.run_file.read_text().splitlines() if line.strip()]
    for row in rows:
        if not row.get("schema_valid"):
            row["verified"], row["verify_failures"] = False, [{"pick_type": "schema", "detail": row.get("error")}]
            row["verify_matches"] = {}
            continue
        row["verify_failures"], row["verify_matches"] = check(row)
        row["verified"] = not row["verify_failures"]
    args.run_file.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"verified {sum(r['verified'] for r in rows)}/{len(rows)} rows in {args.run_file}")


if __name__ == "__main__":
    main()
