"""Triage against a role-matrix standard (the v0.2 YAML format), loaded from a private path.

The standard file is never part of this repository: set ONBOARDING_STANDARD to its path.
When the variable is unset, the endpoint keeps using demo_standard.json (onboarding.py).

The file supplies everything specific to the organisation: version, business_unit {id, name},
venues.in_club, out_of_scope_business_units, out_of_scope_venue_prefixes, aliases, and roles,
each with title, staff_login, company_mailbox and account_role.

Decision order, first match wins (the standard's decision_rules):
  ignored            -> not an onboarding request
  needs_information  -> person name, job title or venue missing; personal email missing or unusable
                        for a role with no company mailbox; trainer level missing; the intake
                        contradicts itself
  human_review       -> out-of-scope unit, duplicate, exception, unmapped title, blank matrix
                        cell (standard_gap), login but no mapped account-system role (role_unmapped)
  recommended        -> role, login yes/no, account-system role, venue, trainer level
Comments go to extraction, as on the demo path. An evaluator grading on intake alone sends
comments=[] itself; that choice belongs to the evaluation, not to the endpoint.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from schema import Recommendation, Request, Response, Status

ENV = "ONBOARDING_STANDARD"
LEVELLED_ROLE = "Personal Trainer"


def configured() -> bool:
    return bool(os.getenv(ENV))


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.casefold()).strip("-")


def _norm(s: str | None) -> str:
    return " ".join((s or "").casefold().split())


def _check(std) -> None:
    """Reject a malformed standard at load time, inside the safe-failure guard."""
    if not isinstance(std, dict) or not isinstance(std.get("roles"), list) or not std["roles"]:
        raise ValueError("standard has no roles")
    if not isinstance(std.get("venues"), dict) or not all(isinstance(v, str) for v in std["venues"].get("in_club", [])):
        raise ValueError("standard venues.in_club must be a list of names")
    unit = std.get("business_unit")
    if not (isinstance(unit, dict) and all(isinstance(unit.get(k), str) and unit[k].strip() for k in ("id", "name"))):
        raise ValueError("standard business_unit needs an id and a name")
    prefixes = std.get("out_of_scope_venue_prefixes", [])
    if not (isinstance(prefixes, list) and all(isinstance(p, str) and p.strip() for p in prefixes)):
        raise ValueError("out_of_scope_venue_prefixes must be a list of names")
    for r in std["roles"]:
        if not isinstance(r, dict) or not isinstance(r.get("title"), str) or not r["title"].strip():
            raise ValueError("every role needs a title")
        for k in ("staff_login", "company_mailbox"):
            # The key must be present: a missing one would read as a blank cell, and a file
            # in an older format would quietly send every ticket to standard_gap.
            if k not in r:
                raise ValueError(f"{r['title']}: {k} is missing")
            if r[k] not in (True, False, None):
                raise ValueError(f"{r['title']}: {k} must be true, false or null")
        if r.get("account_role") is not None and not (isinstance(r["account_role"], str) and r["account_role"].strip()):
            raise ValueError(f"{r['title']}: account_role must be a name or null")
    for k, v in (std.get("aliases") or {}).items():
        if not (isinstance(k, str) and isinstance(v, str)):
            raise ValueError("aliases must map title to title")


@lru_cache(maxsize=4)
def _parse(path: str, mtime_ns: int, size: int) -> dict:  # key includes the file's fingerprint
    import yaml
    std = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    _check(std)
    roles = {_norm(r["title"]): r for r in std["roles"]}
    aliases = {_norm(k): v for k, v in (std.get("aliases") or {}).items()}
    venues = std["venues"]["in_club"]
    return {"version": str(std["version"]), "roles": roles, "aliases": aliases,
            "unit": {"id": std["business_unit"]["id"], "name": std["business_unit"]["name"]},
            "venues": {_norm(v): {"id": "venue-" + _slug(v), "name": v} for v in venues},
            "out_of_scope": {_norm(u) for u in std.get("out_of_scope_business_units", [])},
            "out_of_scope_prefixes": [_norm(p) for p in std.get("out_of_scope_venue_prefixes", [])]}


def _load(path: str) -> dict:
    st = Path(path).stat()  # an edited or removed file is re-read or fails; never served stale
    return _parse(path, st.st_mtime_ns, st.st_size)


_load.cache_clear = _parse.cache_clear  # tests reset the cache through _load


def load_standard() -> dict:
    return _load(os.environ[ENV])


def resolve_role(title: str | None, std: dict):
    t = _norm(title)
    canon = std["aliases"].get(t)
    return std["roles"].get(_norm(canon) if canon else t)


def _out(request, status, reason, **details):
    from onboarding import outcome
    return outcome(request, status, reason, **details)


def recommend_access(request: Request) -> Response:
    from onboarding import ExtractionError, extract_ticket
    try:
        std = load_standard()
    except Exception:  # noqa: BLE001 - any unreadable standard is a safe failure
        return _out(request, Status.FAILED, "The onboarding standard is unavailable; review manually.")
    try:
        facts = extract_ticket(request)
    except ExtractionError as exc:
        return _out(request, Status.FAILED, str(exc))
    return decide(request, facts, std)


# The standard's exception_triggers, checked on the intake text as a backstop to extraction:
# a model can treat a hardware line or "the staff app on a phone" as normal setup; the standard does not.
TRIGGERS = [
    ("re-hire", re.compile(r"re-?hire:\s*yes", re.I)),
    ("transfer or promotion", re.compile(r"\btransfer(?:ring|red|s)?\b|\bpromot(?:ed|ion)\b|title change", re.I)),
    ("mirror or copy another user's access", re.compile(r"\bmirror|\bmimic|same (?:access|permissions?) as|copy (?:of )?\w+'?s? access", re.I)),
    # Standard: "non-standard start (contractor, intern, seasonal)". Seasonal is left out until the matrix
    # owner rules whether a seasonal hire of a standard role gets different access (2026-11-02).
    ("non-standard start", re.compile(r"\b(?:intern(?:ship)?|contractor|temp|temporary)\b", re.I)),
    ("hardware", re.compile(r"\b(?:laptop|monitor|copier|tablet|ipad|iphone)s?\b|(?<!\[)\bphone\b(?!\])", re.I)),
]
ONBOARDING_TYPES = {"employee onboarding"}


def intake_trigger(text: str) -> str | None:
    for name, rx in TRIGGERS:
        if rx.search(text or ""):
            return name
    return None


def _usable_email(email: str | None) -> bool:
    """The same shape check as the demo path: this address becomes the proposed login."""
    local, at, domain = (email or "").partition("@")
    return bool(at and local and domain) and not any(ch.isspace() for ch in email)


def _missing_fields(facts, role) -> list[str]:
    missing = []
    if not facts.person_name:
        missing.append("person_name")
    if not facts.job_title:
        missing.append("job_title")
    if not facts.venue_names or facts.intake_contradiction == "venue":
        missing.append("venue")
    if role and role.get("company_mailbox") is False and (
        not _usable_email(facts.employee_email) or facts.intake_contradiction == "employee_email"
    ):
        missing.append("personal_email")  # a role with a company mailbox never logs in with this address
    if role and role["title"] == LEVELLED_ROLE and role.get("staff_login") and not facts.personal_trainer_level:
        missing.append("personal_trainer_level")
    return missing


def decide(request: Request, facts, std: dict) -> Response:
    """Pure policy: facts + standard -> Response. Tested without a model."""
    kind = _norm(request.issue_type)  # trusted metadata; text in the ticket body cannot set it
    if kind and kind not in ONBOARDING_TYPES:
        return _out(request, Status.IGNORED, f"Issue type '{request.issue_type.strip()}' is not employee onboarding.")
    if facts.request_kind == "other":
        return _out(request, Status.IGNORED, "Not a new-hire onboarding request.")
    role = resolve_role(facts.job_title, std)
    missing = _missing_fields(facts, role)
    if missing:
        return _out(request, Status.NEEDS_INFORMATION, "Provide: " + ", ".join(missing) + ".", missing_fields=missing)

    def review(reason, text):
        details = {"review_reason": reason}
        if reason == "exception":
            details.update(exception_difference=[text], approval_owner_role=None,
                           standard_proposal=_baseline(facts, role, std, names))
        return _out(request, Status.HUMAN_REVIEW, text, **details)

    names = list(dict.fromkeys(_norm(v) for v in facts.venue_names))  # one club named twice is one club
    unit = _norm(facts.business_unit)
    if unit in std["out_of_scope"] or any(_out_of_scope_venue(n, std) for n in names):
        return review("out_of_scope_business_unit", "The venue is outside this standard's scope; route to its owner.")
    if facts.ambiguous_identity:
        return review("ambiguous_identity", "The intake names conflicting identities; resolve who is being onboarded.")
    if facts.marked_duplicate:
        return review("duplicate", "The ticket marks itself a duplicate; confirm before acting.")
    trigger = intake_trigger(request.ticket_text)
    if facts.rehire_transfer_or_promotion or facts.additional_access_request or trigger:
        what = facts.additional_access_request or trigger or "re-hire, transfer, promotion or title change"
        return review("exception", "Requested outside the standard: " + what + ". Assign the standard tier, never a mirror.")
    if role is None:
        return review("ambiguous_mapping", f"The title '{facts.job_title}' is not in the role matrix.")
    if any(n not in std["venues"] for n in names):
        return review("ambiguous_mapping", "A venue does not map to a club in this standard.")
    if role.get("staff_login") is None or role.get("company_mailbox") is None:
        return review("standard_gap", f"The matrix leaves {role['title']} blank; the matrix owner must decide.")
    if role["staff_login"] and not role.get("account_role"):
        return review("role_unmapped", f"{role['title']} gets a login but has no mapped account-system role yet.")

    proposal = build_proposal(facts, role, std, names)
    caveats = ["Existing-account status was not checked."]
    if not facts.start_date:
        caveats.append("The intake gives no start date.")
    if facts.login_required is not None and facts.login_required != role["staff_login"]:
        caveats.append(f"The intake says a login is {'required' if facts.login_required else 'not required'}, but the "
                       f"standard gives {role['title']} {'a login' if role['staff_login'] else 'no login'}; confirm before provisioning.")
    return _out(request, Status.RECOMMENDED,
                f"{role['title']} at {', '.join(v.name for v in proposal.venues)}; login {'yes' if role['staff_login'] else 'no'}.",
                answer=proposal, caveats=caveats)


def _out_of_scope_venue(name: str, std: dict) -> bool:
    return name in std["out_of_scope"] or any(name == p or name.startswith(p + " ") for p in std["out_of_scope_prefixes"])


def _baseline(facts, role, std, names):
    """The standard proposal an exception is compared against, when the standard defines one."""
    if not role or role.get("staff_login") is None or role.get("company_mailbox") is None:
        return None
    if role["staff_login"] and not role.get("account_role"):
        return None
    if not names or any(n not in std["venues"] for n in names):
        return None
    return build_proposal(facts, role, std, names)


def build_proposal(facts, role, std, names) -> Recommendation:
    venues = [std["venues"][n] for n in names]
    level = facts.personal_trainer_level
    if role["staff_login"]:
        assignments = [{"role": {"id": "role-" + _slug(role["account_role"]), "name": role["account_role"]},
                        "scope_type": "venue", "scope": v} for v in venues]
        groups = ([{"staff_group": {"id": f"group-trainer-{level}", "name": f"Trainer Level {level}"},
                    "scope_type": "business_unit", "scope": std["unit"]}] if level and role["title"] == LEVELLED_ROLE else [])
        mailbox = bool(role.get("company_mailbox"))
        login = None if mailbox else facts.employee_email
        steps = [f"Create a staff login for {role['title']}.",
                 *(f"Assign {a['role']['name']} at {a['scope']['name']}." for a in assignments),
                 *(f"Assign staff group {g['staff_group']['name']}." for g in groups)]
    else:
        assignments, groups, login, mailbox = [], [], None, False
        steps = [f"{role['title']} gets no staff login in the standard. Create the member record only."]
    return Recommendation(
        person_name=facts.person_name, job_title=facts.job_title,
        start_date=facts.start_date, staff_login=bool(role["staff_login"]), login_email=login, company_mailbox=mailbox,
        assignments=assignments, permissions=[], venues=venues, standard_version=std["version"],
        matrix_entry_id="role-" + _slug(role["title"]), staff_groups=groups, proposed_changes=steps,
        person_id=facts.person_id,
    )
