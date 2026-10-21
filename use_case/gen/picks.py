"""Deterministic picks and labels for the TC2 synthetic onboarding tickets.

Source of truth: use_case/axes.md (revision 5). No model calls here. Every pick
comes from a seeded rotation, and every label is computed from the picks, the
status rule, and the v0.1 reference tables below.

    python use_case/gen/picks.py --role-fit venue_dependent --one-per-cell
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import datetime, timedelta
from itertools import product

# --- v0.1 reference tables (axes.md "Reference data") -----------------------

CLUBS = ["Club A", "Club B", "Club C", "Club D", "Club E"]

# standard role -> (department, login): True/False, or None for "by club"
ROLES = {
    "Group Fitness Instructor": ("Group Fitness", True),
    "Personal Trainer": ("Personal Training", True),
    "Front Desk Associate": ("Front Desk", True),
    "Massage Therapist": ("Front Desk", True),
    "Membership Consultant": ("Membership Sales", True),
    "Cafe Associate": ("Cafe", False),
    "Housekeeping Associate": ("Housekeeping", False),
    "Lifeguard": ("Aquatics", None),
    "Aquatics Lead": ("Aquatics", None),
}

# role -> clubs where login IS required; every other club: not required
VENUE_LOGIN = {"Lifeguard": {"Club C"}, "Aquatics Lead": {"Club A", "Club C"}}

# Departments for outside-standard titles are not in axes.md; generic placeholders.
OUTSIDE_STANDARD = {
    "Carpenter": "Facilities",
    "Special Events Assistant": "Events",
    "Department Manager": "Operations",
    "Assistant General Manager": "Club Management",
    "Foundation Coordinator": "Foundation",
    "Babysitter": "Child Care",
}

REFERENCE_VERSIONS = {"role_list": "v0.1", "club_access": "v0.1", "status_rule": "provisional-1"}

# --- axes --------------------------------------------------------------------

ROLE_FIT = ["exact", "near_match", "venue_dependent", "outside_standard"]
INTENT = ["new_hire", "returning_or_moving"]
RELIABILITY = ["clean", "missing_required", "internal_contradiction", "changed_after_submission"]
# Every onboarding ticket carries two jobs: (1) a member record in the club-management
# system (every employee), and (2) a staff login with a role (role-dependent).
SCOPE = ["member_plus_staff_login", "member_record_only", "beyond_template"]

# Fixed-login roles used for `exact`. Lifeguard and Aquatics Lead are by-club and
# belong to `venue_dependent`; using them here would blur the two values.
EXACT_LOGIN_YES = [r for r, (_, login) in ROLES.items() if login is True]
EXACT_LOGIN_NO = [r for r, (_, login) in ROLES.items() if login is False]

# Extra requests for beyond_template. `keywords` is what verify.py looks for.
EXTRA_REQUESTS = [
    {"kind": "hardware", "text": "a dedicated laptop and a desk phone", "keywords": ["laptop", "desk phone"]},
    {"kind": "hardware", "text": "a tablet for the front counter", "keywords": ["tablet"]},
    {"kind": "systems", "text": "access to the payroll portal and the scheduling system", "keywords": ["payroll portal", "scheduling system"]},
    {"kind": "systems", "text": "access to the marketing email tool", "keywords": ["marketing email tool"]},
    {"kind": "same_as", "text": "same access as Jordan Sample", "keywords": ["same access as", "Jordan Sample"]},
    {"kind": "same_as", "text": "same access as Riley Placeholder", "keywords": ["same access as", "Riley Placeholder"]},
]

INTENT_NOTES = ["returning", "transferring", "promoted"]

# Seeded fictional names. Code picks requester, manager, and employee per row; the
# model must use them as given. Emails are derived as first.last@example.com.
FIRST_NAMES = ["Arlo", "Bexley", "Caspian", "Delphine", "Ezra", "Fennimore", "Gwendolyn", "Hollis",
               "Isolde", "Jasper", "Kestrel", "Lark", "Marisol", "Nico", "Ottoline", "Percival",
               "Quinlan", "Rosalind", "Sorrel", "Tobias", "Ulla", "Vesper", "Wren", "Xavi", "Yara", "Zephyr"]
LAST_NAMES = ["Ashgrove", "Brindlewood", "Copperfield", "Dunmore", "Elderberry", "Foxglove", "Gallowmere",
              "Hartwell", "Inglenook", "Juniperhill", "Kettleby", "Larkspur", "Mossbank", "Nettlefield",
              "Oakhollow", "Pebbleton", "Quenby", "Ravensworth", "Saltmarsh", "Thistledown", "Underhill",
              "Wexcombe", "Yarrowby"]

FIXED_ROWS = [
    {"n": 1, "kind": "login_problem", "request_type": "Get IT help",
     "brief": "An existing employee reports they cannot log in to the club-management system.",
     "status": "ignored", "reason": "not_onboarding_request"},
    {"n": 2, "kind": "permission_change", "request_type": "Request a change",
     "brief": "A manager asks to change permissions for an existing employee.",
     "status": "ignored", "reason": "not_onboarding_request"},
    {"n": 3, "kind": "outage", "request_type": "Report an outage",
     "brief": "Staff report that the club-management system client will not open at the front desk.",
     "status": "ignored", "reason": "not_onboarding_request"},
    {"n": 4, "kind": "offboarding", "request_type": "Offboarding",
     "brief": "A manager asks to remove access for an employee whose last day is this week.",
     "status": "ignored", "reason": "not_onboarding_request"},
    {"n": 5, "kind": "promotion_general", "request_type": "General service request",
     "brief": "A manager says an existing employee was promoted and needs updated access, filed as a general request.",
     "status": "ignored", "reason": "wrong_channel"},
    {"n": 6, "kind": "vague_account", "request_type": "General service request",
     "brief": "Someone writes only that they need their own account. No role, club, or manager is given.",
     "status": "needs_information", "reason": "vague_request"},
]

ONBOARDING_REQUEST_TYPE = "New Hire Onboarding"

# Fixed-row situations about an employee other than the requester.
FIXED_WITH_EMPLOYEE = {"permission_change", "offboarding", "promotion_general"}

EXPECTED_MIX = {"recommended": 36, "needs_information": 49, "human_review": 36, "ignored": 5}
EXPECTED_TOTAL = 126


def status_for(role_fit: str, intent: str, reliability: str, scope: str) -> str:
    """axes.md status rule, first match wins. Rule 1 (not onboarding) is fixed rows only."""
    if reliability in ("missing_required", "internal_contradiction"):
        return "needs_information"
    if role_fit == "outside_standard" or intent == "returning_or_moving" or scope == "beyond_template":
        return "human_review"
    return "recommended"


def reason_for(role_fit: str, intent: str, reliability: str, scope: str, picks: dict) -> str | None:
    status = status_for(role_fit, intent, reliability, scope)
    if status == "needs_information":
        if reliability == "missing_required":
            return f"missing_required:{picks['blank_field']}"
        return f"internal_contradiction:{picks['contradiction_variant']}"
    if status == "human_review":
        triggers = [t for t, hit in (
            ("outside_standard", role_fit == "outside_standard"),
            ("returning_or_moving", intent == "returning_or_moving"),
            ("beyond_template", scope == "beyond_template"),
        ) if hit]
        return "human_review:" + "+".join(triggers)
    return None


def standard_login(role: str, club: str | None) -> bool | None:
    login = ROLES[role][1]
    if login is not None:
        return login
    return None if club is None else club in VENUE_LOGIN[role]


def ticket_login(scope: str) -> bool:
    return scope != "member_record_only"


class Rotation:
    """A seeded, shuffled cycle. `take` skips items failing `where` or in `exclude`."""

    def __init__(self, rng: random.Random, items):
        self.items = list(items)
        rng.shuffle(self.items)
        self.i = 0

    def take(self, where=lambda _: True, exclude=()):
        for _ in range(len(self.items)):
            item = self.items[self.i % len(self.items)]
            self.i += 1
            if item not in exclude and where(item):
                return item
        raise ValueError(f"no item satisfies the constraint in {self.items}")


def pick_people(rot: dict, roles: tuple[str, ...]) -> dict:
    """Distinct fictional names (and example.com emails) for the given ticket roles."""
    people, used = {}, set()
    for role in roles:
        first = rot["first"].take(exclude={n.split()[0] for n in used})
        last = rot["last"].take()
        used.add(f"{first} {last}")
        people[f"{role}_name"] = f"{first} {last}"
        people[f"{role}_email"] = f"{first}.{last}@example.com".lower()
    return people


def build_plan(seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rot = {
        "exact_yes": Rotation(rng, EXACT_LOGIN_YES),
        "exact_no": Rotation(rng, EXACT_LOGIN_NO),
        "exact_any": Rotation(rng, EXACT_LOGIN_YES + EXACT_LOGIN_NO),
        "near_variant": Rotation(rng, ["a", "b", "c"]),
        "level": Rotation(rng, [1, 2, 3]),
        "venue_role": Rotation(rng, list(VENUE_LOGIN)),
        "outside": Rotation(rng, list(OUTSIDE_STANDARD)),
        "club": Rotation(rng, CLUBS),
        "blank_any": Rotation(rng, ["due_date", "location", "employee_email"]),
        "blank_venue": Rotation(rng, ["due_date", "employee_email"]),
        "contradiction": Rotation(rng, ["a", "b"]),
        "changed": Rotation(rng, ["due_date", "club"]),  # the member record is never changed
        "intent_note": Rotation(rng, INTENT_NOTES),
        "first": Rotation(rng, FIRST_NAMES),
        "last": Rotation(rng, LAST_NAMES),
        "extra": Rotation(rng, range(len(EXTRA_REQUESTS))),
        "day": Rotation(rng, range(45)),
        "hour": Rotation(rng, range(8, 18)),
        "minute": Rotation(rng, [0, 5, 12, 20, 33, 41, 47, 55]),
        "lead_days": Rotation(rng, range(10, 36)),
        "date_shift": Rotation(rng, [-7, -5, -3, 3, 4, 7, 10, 14]),
        "comment_hours": Rotation(rng, [3, 6, 20, 26, 49, 70]),
    }
    base = datetime(2026, 9, 1)
    rec_cell_index = Counter()  # per (role_fit, scope), for Rule 4's alternating start side
    rows = []

    for role_fit, intent, reliability, scope in product(ROLE_FIT, INTENT, RELIABILITY, SCOPE):
        cell_id = f"{role_fit}|{intent}|{reliability}|{scope}"
        status = status_for(role_fit, intent, reliability, scope)
        n_rows = 3 if status == "recommended" else 1
        if status == "recommended":
            # Staggered by scope too, so each scope gets a balanced agree/disagree split.
            start_agree = (rec_cell_index[(role_fit, scope)] + SCOPE.index(scope)) % 2 == 0
            rec_cell_index[(role_fit, scope)] += 1

        for k in range(n_rows):
            # Rule 4: alternate agree/disagree within recommended cells.
            want_agree = (start_agree if k % 2 == 0 else not start_agree) if status == "recommended" else None
            want_login = None
            if want_agree is not None:
                want_login = ticket_login(scope) if want_agree else not ticket_login(scope)

            created = base + timedelta(days=rot["day"].take(), hours=rot["hour"].take(), minutes=rot["minute"].take())
            due = (created + timedelta(days=rot["lead_days"].take())).date()
            picks = {
                "title": None, "standard_role": None, "level": None, "department": None,
                "club": None, "near_match_variant": None, "blank_field": None,
                "contradiction_variant": None, "contradiction_club": None,
                "changed": None, "comment_ts": None, "extra_request": None,
                "previous_club": None, "intent_note": None,
                "created": created.isoformat(timespec="seconds"), "due_date": due.isoformat(),
                "request_type": ONBOARDING_REQUEST_TYPE,
                **pick_people(rot, ("requester", "manager", "employee")),
            }

            # Axis 3 first (Rule 1: Axis 3 wins), so later axes can respect its picks.
            if reliability == "missing_required":
                if role_fit == "exact":
                    picks["blank_field"] = "job_title"  # Rule 2
                elif role_fit == "venue_dependent":
                    picks["blank_field"] = rot["blank_venue"].take()  # never blank location
                else:
                    picks["blank_field"] = rot["blank_any"].take()
            elif reliability == "internal_contradiction":
                picks["contradiction_variant"] = rot["contradiction"].take()
            elif reliability == "changed_after_submission":
                picks["changed"] = {"detail": rot["changed"].take(), "from": None, "to": None}
                picks["comment_ts"] = (created + timedelta(hours=rot["comment_hours"].take())).isoformat(timespec="seconds")

            changed_detail = picks["changed"]["detail"] if picks["changed"] else None

            # Axis 1: role and club.
            role = None
            club = None
            club_after = None
            if role_fit == "exact":
                if want_login is True:
                    role = rot["exact_yes"].take()
                elif want_login is False:
                    role = rot["exact_no"].take()
                else:
                    role = rot["exact_any"].take()
                picks["title"] = role
            elif role_fit == "near_match":
                variant = rot["near_variant"].take()
                picks["near_match_variant"] = variant
                if variant == "a":
                    picks["level"] = rot["level"].take()
                    role, picks["title"] = "Front Desk Associate", f"Hospitality Associate Level {picks['level']}"
                elif variant == "b":
                    picks["level"] = rot["level"].take()
                    role, picks["title"] = "Personal Trainer", f"Level {picks['level']} Personal Trainer"
                else:
                    role, picks["title"] = "Front Desk Associate", "Hospitality Associate"
            elif role_fit == "venue_dependent":
                role = rot["venue_role"].take()
                picks["title"] = role
                if want_login is not None and changed_detail == "club":
                    # Rule 4: agreement is computed from the club AFTER the change.
                    club_after = rot["club"].take(where=lambda c: (c in VENUE_LOGIN[role]) == want_login)
                    club = rot["club"].take(exclude={club_after})
                elif want_login is not None:
                    club = rot["club"].take(where=lambda c: (c in VENUE_LOGIN[role]) == want_login)
            else:
                picks["title"] = rot["outside"].take()

            if club is None:
                club = rot["club"].take()
            if changed_detail == "club" and club_after is None:
                club_after = rot["club"].take(exclude={club})

            picks["standard_role"] = role
            picks["department"] = ROLES[role][0] if role else OUTSIDE_STANDARD[picks["title"]]
            picks["club"] = club

            if picks["blank_field"] == "job_title":
                picks["title"] = None
            if picks["blank_field"] == "location":
                picks["club"] = None
            if picks["contradiction_variant"] == "a":
                picks["contradiction_club"] = rot["club"].take(exclude={club})

            if changed_detail == "due_date":
                new_due = due + timedelta(days=rot["date_shift"].take())
                if new_due <= created.date():
                    new_due = due + timedelta(days=7)
                picks["changed"].update({"from": due.isoformat(), "to": new_due.isoformat()})
            elif changed_detail == "club":
                picks["changed"].update({"from": club, "to": club_after})

            # Axis 2.
            if intent == "returning_or_moving":
                picks["intent_note"] = rot["intent_note"].take()
                picks["previous_club"] = rot["club"].take(exclude={club, club_after})

            # Axis 4.
            if scope == "beyond_template":
                picks["extra_request"] = EXTRA_REQUESTS[rot["extra"].take()]

            rows.append(_label(cell_id, role_fit, intent, reliability, scope, picks, k))

    for fx in FIXED_ROWS:
        created = base + timedelta(days=rot["day"].take(), hours=rot["hour"].take(), minutes=rot["minute"].take())
        rows.append({
            "row_id": f"fixed|{fx['n']}#0",
            "cell_id": f"fixed|{fx['n']}",
            "axes": None,
            "fixed": {"n": fx["n"], "kind": fx["kind"], "brief": fx["brief"]},
            "picks": {"request_type": fx["request_type"], "created": created.isoformat(timespec="seconds"),
                      "club": None if fx["kind"] == "vague_account" else rot["club"].take(),
                      # Fixed rows that name another employee get that name from code too.
                      **pick_people(rot, ("requester", "employee") if fx["kind"] in FIXED_WITH_EMPLOYEE
                                    else ("requester",))},
            "expected_status": fx["status"],
            "role_fit_observable": False,
            "expected_proposal": None,
            "expected_caveat": None,
            "expected_reason": fx["reason"],
            "reference_versions": REFERENCE_VERSIONS,
        })

    mix = Counter(r["expected_status"] for r in rows)
    assert len(rows) == EXPECTED_TOTAL, f"plan has {len(rows)} rows, expected {EXPECTED_TOTAL}"
    assert dict(mix) == EXPECTED_MIX, f"status mix {dict(mix)} != {EXPECTED_MIX}"
    return rows


def _label(cell_id, role_fit, intent, reliability, scope, picks, k) -> dict:
    status = status_for(role_fit, intent, reliability, scope)
    proposal = None
    caveat = None
    if status == "recommended":
        changed = picks["changed"] or {}
        club = changed["to"] if changed.get("detail") == "club" else picks["club"]
        login = standard_login(picks["standard_role"], club)  # Rule 3: the standard wins
        proposal = {
            "standard_role": picks["standard_role"],
            "level": picks["level"],
            "club": club,
            "login_required": login,
            "membership_required": True,  # the member record follows the ticket and is always created
            "extra_requests": [],
        }
        if login != ticket_login(scope):
            caveat = "request_differs_from_standard"
    return {
        "row_id": f"{cell_id}#{k}",
        "cell_id": cell_id,
        "axes": {"role_fit": role_fit, "intent": intent, "reliability": reliability, "scope": scope},
        "fixed": None,
        "picks": picks,
        "expected_status": status,
        "role_fit_observable": picks["blank_field"] != "job_title",
        "expected_proposal": proposal,
        "expected_caveat": caveat,
        "expected_reason": reason_for(role_fit, intent, reliability, scope, picks),
        "reference_versions": REFERENCE_VERSIONS,
    }


def select(rows: list[dict], role_fit: str | None = None, one_per_cell: bool = False, limit: int | None = None,
           fixed_only: bool = False) -> list[dict]:
    if fixed_only:
        rows = [r for r in rows if r["fixed"]]
    if role_fit:
        rows = [r for r in rows if r["axes"] and r["axes"]["role_fit"] == role_fit]
    if one_per_cell:
        seen, kept = set(), []
        for r in rows:
            if r["cell_id"] not in seen:
                seen.add(r["cell_id"])
                kept.append(r)
        rows = kept
    return rows[:limit] if limit else rows


def add_filter_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--role-fit", choices=ROLE_FIT)
    p.add_argument("--one-per-cell", action="store_true")
    p.add_argument("--fixed-only", action="store_true")
    p.add_argument("--limit", type=int)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_filter_args(p)
    args = p.parse_args()
    rows = select(build_plan(args.seed), args.role_fit, args.one_per_cell, args.limit, args.fixed_only)
    for r in rows:
        sys.stdout.write(json.dumps(r) + "\n")
    print(f"{len(rows)} rows; status mix {dict(Counter(r['expected_status'] for r in rows))}", file=sys.stderr)


if __name__ == "__main__":
    main()
