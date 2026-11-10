"""Triage against a role-matrix standard (the v0.2 YAML format), loaded from a private path.

The standard file is never part of this repository. Point the endpoint at it one of two ways:
  ONBOARDING_STANDARD=<path>        one file, used as is (wins over the two below)
  ONBOARDING_STANDARD_DIR=<dir>     the private folder holding onboarding_standard_v<N>_scrubbed_loader.yaml,
  ONBOARDING_STANDARD_VERSION=<N>   with the version to load: 0.5 by default (2026-11-10). TC4 stays pinned
                                    to 0.3 (TC4_VERSION; owner decision 2026-11-07) and is never rescored on 0.4.
A file chosen by version must say that version, or the endpoint fails safely rather than mislabel a run.
When none is set, the endpoint keeps using demo_standard.json (onboarding.py).

The file supplies everything specific to the organisation: version, business_unit {id, name},
venues.in_club, out_of_scope_business_units, out_of_scope_venue_prefixes, aliases, and roles,
each with title, staff_login, company_mailbox and account_role.

Decision order, first match wins (the standard's decision_rules, except the re-hire order below,
confirmed by the owner 2026-11-07; transfers and promotions follow the same rule. The private v0.3
runner behind the saved TC4 runs predates it and still asks first):
  ignored            -> not an onboarding request
  needs_information  -> person name without a surname (has_surname), job title or venue missing; a pool role
                        (Lifeguard, Aquatics Lead) at a club not in pool_clubs (venue_confirmation; once the
                        requester confirms the club, it becomes an exception review instead);
                        personal email missing or unusable
                        for a role with no company mailbox; trainer level missing; the intake
                        contradicts itself. Not for a re-hire, transfer or promotion: see exception
  human_review       -> out-of-scope unit, ambiguous identity, duplicate; then exception, which a
                        re-hire ("Re-hire: YES") or a flagged re-hire, transfer or promotion (the
                        extracted flag) reaches even with facts
                        missing, listing them in review_missing_fields / contradictory_fields and
                        the comment, with no standard proposal (TC5: an ask would be a wasted round
                        trip); then unmapped title, blank matrix cell (standard_gap), login but
                        no mapped account-system role (role_unmapped)
  recommended        -> role, login yes/no, account-system role, venue, trainer level
An exception review names its approver (approval_owner_role): the Service Desk Manager for a re-hire,
transfer or promotion, otherwise the role's business-unit owner (BUSINESS_UNIT_OWNERS). A club manager's owner is
the General Manager of the ticket's one club; a ticket naming several clubs, or none, goes to the Service Desk Manager.
Comments go to extraction, as on the demo path. An evaluator grading on intake alone sends
comments=[] itself; that choice belongs to the evaluation, not to the endpoint.
"""
from __future__ import annotations

import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from schema import Recommendation, Request, Response, Status

ENV = "ONBOARDING_STANDARD"
DIR_ENV = "ONBOARDING_STANDARD_DIR"
VERSION_ENV = "ONBOARDING_STANDARD_VERSION"
FILENAME = "onboarding_standard_v{version}_scrubbed_loader.yaml"
DEFAULT_VERSION = "0.5"  # from 2026-11-10 (owner rulings); 0.4 stays loadable by version
TC4_VERSION = "0.3"  # frozen for TC4 (owner decision 2026-11-07): its evals and baseline load 0.3 explicitly
LEVELLED_ROLE = "Personal Trainer"
POOL_ROLES = ("Lifeguard", "Aquatics Lead")  # the standard's pool_roles list wins when it has one
SERVICE_DESK_MANAGER = "Service Desk Manager"
# Exception approver = the role's business-unit owner (owner decision 2026-11-07), keyed by the matrix's role group.
# The routing (exceptions -> business-unit owner; re-hire, transfer, promotion -> Service Desk Manager) was confirmed
# by the service desk on 2026-11-09. The owner per group was assigned by the project owner on 2026-11-10.
# Group Fitness: two of the three leaders the 2026-11-04 call named; the VP is left out by the owner (see decisions.md).
# A group not listed here, or a title not in the matrix, goes to the Service Desk Manager, who holds and routes it.
# A tuple means either role can approve; the output names them joined by "or", in this order.
# Managers: the General Manager of the ticket's club (business development manager's review, 2026-11-10).
CLUB_GENERAL_MANAGER = "General Manager of the ticket's club"
BUSINESS_UNIT_OWNERS = {
    "Accounting": "VP of Finance (Fitness)",
    "Aquatics": "VP of Operations (Fitness)",
    "Cafe": "Food & Beverage Director",
    "Childcare": ("VP Hospitality", "Business Development Manager (Fitness)"),
    "Group Fitness": ("Senior Group Fitness Manager", "Group Fitness Director"),
    "Hospitality": ("VP Hospitality", "Business Development Manager (Fitness)"),
    "Housekeeping": "VP of Operations (Fitness)",
    "Human Resources": "HR / People Ops Director",
    "Maintenance": "VP of Operations (Fitness)",
    "Managers": CLUB_GENERAL_MANAGER,
    "Marketing": "VP Marketing",
    "Massage": ("VP Hospitality", "Business Development Manager (Fitness)"),
    "Member Services": ("VP Hospitality", "Business Development Manager (Fitness)"),
    "Membership Sales": "VP of Membership Sales (Fitness)",
    "Personal Training": "Director of Personal Training",
    "Rockwall": "General Manager (Club A)",  # the only club with a rockwall
    "Special Events": "Events Director",
    "Technology": ("Senior Director IT", "CTO"),
}


def configured() -> bool:
    return bool(os.getenv(ENV) or os.getenv(DIR_ENV))


def standard_path(version: str | None = None) -> str:
    """The file to load: the explicit path, else the requested (or configured, or default) version in the directory."""
    if version is None and os.getenv(ENV):
        return os.environ[ENV]
    version = version or os.getenv(VERSION_ENV) or DEFAULT_VERSION
    if not re.fullmatch(r"\d+\.\d+", version):
        raise ValueError(f"{VERSION_ENV} must look like 0.4, not {version!r}")
    if not os.getenv(DIR_ENV):
        raise ValueError(f"standard v{version} was asked for by version, but {DIR_ENV} is not set")
    return str(Path(os.environ[DIR_ENV]) / FILENAME.format(version=version))


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
        if r.get("group") is not None and not isinstance(r["group"], str):
            raise ValueError(f"{r['title']}: group must be a name or null")  # the approver lookup keys on it
    for k, v in (std.get("aliases") or {}).items():
        if not (isinstance(k, str) and isinstance(v, str)):
            raise ValueError("aliases must map title to title")
    if not isinstance(std.get("version"), str):
        # Unquoted YAML turns 0.10 into 0.1, and the version check against the file name would then fail every ticket.
        raise ValueError("version must be a quoted string")
    pool = std.get("pool_clubs") or []
    if not (isinstance(pool, list) and all(isinstance(v, str) and v in std["venues"].get("in_club", []) for v in pool)):
        raise ValueError("pool_clubs must be a list of clubs from venues.in_club")
    nbs = std.get("non_bundle_systems") or []
    if not (isinstance(nbs, list) and all(isinstance(x, str) and x.strip() for x in nbs)):
        raise ValueError("non_bundle_systems must be a list of system names")
    pool_roles = std.get("pool_roles", POOL_ROLES)
    if not (isinstance(pool_roles, (list, tuple)) and all(isinstance(t, str) and t.strip() for t in pool_roles)):
        raise ValueError("pool_roles must be a list of titles")
    # A misspelt rule would switch the pool rule off silently, and the missed asks it clears would come back.
    if pool and std.get("pool_roles_outside_pool_club") != "needs_information":
        raise ValueError("pool_roles_outside_pool_club must be needs_information when pool_clubs is set")


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
            "out_of_scope_prefixes": [_norm(p) for p in std.get("out_of_scope_venue_prefixes", [])],
            "pool_clubs": {_norm(v) for v in std.get("pool_clubs") or []},
            "pool_roles": {_norm(t) for t in std.get("pool_roles", POOL_ROLES)},
            # Systems outside every role's bundle, named by the standard. An intake that names one is an exception.
            "non_bundle_systems": [(n, re.compile(r"(?<![\w.])" + re.escape(n) + r"(?![\w])", re.I))
                                   for n in std.get("non_bundle_systems") or []]}


def _load(path: str) -> dict:
    st = Path(path).stat()  # an edited or removed file is re-read or fails; never served stale
    return _parse(path, st.st_mtime_ns, st.st_size)


_load.cache_clear = _parse.cache_clear  # tests reset the cache through _load


def load_standard(version: str | None = None) -> dict:
    """The configured standard, or a named version. A chosen version must match the file.

    The TC4 runner (private, outside this repo) passes TC4_VERSION; run.py --committed checks the saved baseline's pin.
    """
    std = _load(standard_path(version))
    # An explicit path is checked only when a version is also given; otherwise the version in force is checked.
    wanted = version or os.getenv(VERSION_ENV) or (None if os.getenv(ENV) else DEFAULT_VERSION)
    if wanted and std["version"] != wanted:
        raise ValueError(f"asked for standard v{wanted}, the file says v{std['version']}")
    return std


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


def intake_triggers(text: str) -> list[str]:
    """Every exception trigger the intake text hits, in TRIGGERS order."""
    return [name for name, rx in TRIGGERS if rx.search(text or "")]


def intake_trigger(text: str) -> str | None:
    found = intake_triggers(text)
    return found[0] if found else None


def _usable_email(email: str | None) -> bool:
    """The same shape check as the demo path: this address becomes the proposed login."""
    local, at, domain = (email or "").partition("@")
    return bool(at and local and domain) and not any(ch.isspace() for ch in email)


_EDGE_PUNCTUATION = ".,;:()[]<>\"'’"
_INNER_NAME_MARKS = "-'’"
# Titles and generational suffixes are not name parts: "Mr Smith" and "Sam Jr." each have one.
_NOT_NAME_PARTS = {"mr", "mrs", "ms", "mx", "miss", "dr", "jr", "sr", "ii", "iii", "iv"}


def _letter(c: str) -> bool:
    # Combining marks count: Devanagari vowel signs, and accents left decomposed after normalising.
    return c.isalpha() or unicodedata.category(c).startswith("M")


def _name_token(t: str) -> bool:
    return (sum(c.isalpha() for c in t) >= 2 and t.casefold() not in _NOT_NAME_PARTS
            and all(_letter(c) or c in _INNER_NAME_MARKS for c in t))


def has_surname(name: str | None) -> bool:
    """True when the name has a given name and a surname: at least two name tokens. Pure, no model call.

    Owner's name policy, 2026-11-07: a legal surname is required; without one the intake goes back to the
    requesting manager. A name token is letters (combining marks included), optionally joined by a hyphen or
    apostrophe ("García-López", "O'Neill"), with at least two letters, so an initial ("S.") is not one. A token
    with "@", a dot inside a word, an underscore or a digit is a handle, not a name, and does not count
    ("sam.smith", "rq4471"); an email beside a full name is ignored. Titles and suffixes ("Mr", "Jr.") do not count.
    Limit: names written without spaces (e.g. Chinese) are one token, so they are asked for; a reviewer decides.
    """
    tokens = [t.strip(_EDGE_PUNCTUATION) for t in unicodedata.normalize("NFC", name or "").split()]
    return sum(_name_token(t) for t in tokens if t) >= 2


def _field_label(field: str, facts) -> str:
    """The field name the requester and the reviewer read: a given name without a surname says so."""
    if field == "person_name" and facts.person_name and facts.person_name.strip():
        return "person_name (a name was given without a legal surname)"
    if field == "venue_confirmation":
        return "venue_confirmation (a pool role at a club with no pool; confirm the club)"
    return field


def _pool_venue_unconfirmed(role, names: list[str], std: dict) -> bool:
    """A pool role at an in-scope club with no pool: the requester confirms the venue (v0.4 pool rule)."""
    return bool(role and _norm(role["title"]) in std.get("pool_roles", ()) and std.get("pool_clubs")
                and any(n in std["venues"] and n not in std["pool_clubs"] for n in names))


def _approver(role, desk: bool, names: list[str], std: dict | None) -> str:
    """Who approves an exception: the desk for a re-hire, transfer or promotion, else the business-unit owner.

    A club manager's owner is the General Manager of the ticket's club, so it needs exactly one known club;
    several clubs or none go to the Service Desk Manager, who holds and routes.
    """
    if desk:
        return SERVICE_DESK_MANAGER
    owner = BUSINESS_UNIT_OWNERS.get((role or {}).get("group"), SERVICE_DESK_MANAGER)
    if owner == CLUB_GENERAL_MANAGER:
        if std and len(names) == 1 and names[0] in std["venues"]:
            return f"General Manager ({std['venues'][names[0]]['name']})"
        return SERVICE_DESK_MANAGER
    return " or ".join(owner) if isinstance(owner, tuple) else owner


def _missing_fields(facts, role, std, names) -> list[str]:
    missing = []
    if not has_surname(facts.person_name):  # empty, first name only, initials or a handle: ask for the legal name
        missing.append("person_name")
    if not facts.job_title:
        missing.append("job_title")
    if not facts.venue_names or facts.intake_contradiction == "venue":
        missing.append("venue")
    elif _pool_venue_unconfirmed(role, names, std) and not getattr(facts, "venue_confirmed", False):
        missing.append("venue_confirmation")
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
    names = list(dict.fromkeys(_norm(v) for v in facts.venue_names))  # one club named twice is one club
    missing = _missing_fields(facts, role, std, names)
    triggers = intake_triggers(request.ticket_text)
    named = [n for n, rx in std.get("non_bundle_systems", ()) if rx.search(request.ticket_text or "")]
    if named:  # a deterministic backstop: extraction missed "needs Prospr" and "all Zoho accounts" (TC5 test)
        triggers.append("systems beyond the role bundle: " + ", ".join(named))
    trigger = triggers[0] if triggers else None
    # A re-hire needs a person whatever the requester answers, so asking first only adds a round trip: it skips
    # the ask and reaches the exception review below with the gaps listed. Only "Re-hire: YES" and the extracted
    # flag count; the broad transfer/promotion regex would let a stray "promotion" suppress a needed ask.
    rehire = facts.rehire_transfer_or_promotion or trigger == "re-hire"
    # Owner, 2026-11-10: any exception needs a person whatever the requester answers, so it skips the ask too
    # (extra access, mirror, non-standard start, hardware). The broad transfer/promotion regex alone does not.
    exception = rehire or bool(facts.additional_access_request) or any(
        t not in ("re-hire", "transfer or promotion") for t in triggers)
    if missing and not exception:
        return _out(request, Status.NEEDS_INFORMATION, "Provide: " + ", ".join(_field_label(f, facts) for f in missing) + ".",
                    missing_fields=missing)

    # Only an exception reaches review with gaps (it skipped the ask), so whichever review it lands in must
    # still hand them over: the exception branch as data and prose, the earlier three in the comment.
    absent, contradictory = _gaps(facts, missing)
    gaps_text = _gaps_sentence([_field_label(f, facts) for f in absent], contradictory)

    def review(reason, text):
        return _out(request, Status.HUMAN_REVIEW, text + gaps_text, review_reason=reason)

    unit = _norm(facts.business_unit)
    if unit in std["out_of_scope"] or any(_out_of_scope_venue(n, std) for n in names):
        return review("out_of_scope_business_unit", "The venue is outside this standard's scope; route to its owner.")
    if facts.ambiguous_identity:
        return review("ambiguous_identity", "The intake names conflicting identities; resolve who is being onboarded.")
    if facts.marked_duplicate:
        return review("duplicate", "The ticket marks itself a duplicate; confirm before acting.")
    # A re-hire with gaps always reaches this branch (rehire implies the condition), after the three checks above,
    # so one that is also out of scope or a duplicate keeps that reason.
    # Service desk, 2026-11-09: a pool role at a club with no pool, once the requester confirms the club,
    # goes to a person (the business-unit owner) rather than being asked again or refused.
    pool_confirmed = getattr(facts, "venue_confirmed", False) and _pool_venue_unconfirmed(role, names, std)
    if facts.rehire_transfer_or_promotion or facts.additional_access_request or trigger or pool_confirmed:
        # Every reason, not the first found: a re-hire that also asks for extra access, or whose intake also
        # asks to mirror a colleague, must say both.
        reasons = [facts.additional_access_request, *triggers,
                   "pool role at a club with no pool (requester confirmed the club)" if pool_confirmed else None,
                   # The flag names its own reason unless "Re-hire: YES" already did. Another trigger, even the broad
                   # transfer/promotion one, does not say why the ask was skipped.
                   "re-hire, transfer, promotion or title change"
                   if facts.rehire_transfer_or_promotion and "re-hire" not in triggers else None]
        differences = list(dict.fromkeys(r for r in reasons if r))  # the access beyond the standard, nothing else
        # No tier is built on facts the intake lacks or contradicts: the reviewer gets the gaps instead.
        baseline = None if missing else _baseline(facts, role, std, names)
        text = "Requested outside the standard: " + "; ".join(differences) + "." + gaps_text
        text += (" Assign the standard tier, never a mirror." if baseline else
                 " No standard tier can be proposed yet; never mirror another user's access.")
        # A transfer or promotion the intake names counts too, even when extraction did not flag it.
        approver = _approver(role, rehire or "transfer or promotion" in triggers, names, std)
        text += f" Approver: {approver}."
        return _out(request, Status.HUMAN_REVIEW, text, review_reason="exception",
                    exception_difference=differences, approval_owner_role=approver, standard_proposal=baseline,
                    review_missing_fields=absent, contradictory_fields=contradictory)
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
    if role.get("caveat"):  # a standing warning the owner attached to this title's grant (e.g. a known over-broad role)
        caveats.append(role["caveat"])
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


def _gaps(facts, missing: list[str]) -> tuple[list[str], list[str]]:
    """For a re-hire that skipped the ask: (fields absent from the intake, fields it gives but contradicts)."""
    present = {"venue": bool(facts.venue_names), "personal_email": _usable_email(facts.employee_email)}
    conflict = {"venue": "venue", "employee_email": "personal_email"}.get(facts.intake_contradiction)
    contradictory = [f for f in missing if f == conflict and present.get(f)]
    return [f for f in missing if f not in contradictory], contradictory


def _gaps_sentence(absent: list[str], contradictory: list[str]) -> str:
    """The same gaps as the structured fields, in the comment the reviewer reads."""
    parts = ([f"Missing from the intake: {', '.join(absent)}."] if absent else []) + \
            ([f"Contradictory in the intake: {', '.join(contradictory)}."] if contradictory else [])
    return " " + " ".join(parts) + " Resolve them during review." if parts else ""


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
        role_ref = {"id": "role-" + _slug(role["account_role"]), "name": role["account_role"]}
        if role.get("account_role_scope") == "business_unit":  # granted once at the business unit, not per club
            assignments = [{"role": role_ref, "scope_type": "business_unit", "scope": std["unit"]}]
        else:
            assignments = [{"role": role_ref, "scope_type": "venue", "scope": v} for v in venues]
        groups = ([{"staff_group": {"id": f"group-trainer-{level}", "name": f"Trainer Level {level}"},
                    "scope_type": "business_unit", "scope": std["unit"]}] if level and role["title"] == LEVELLED_ROLE else [])
        if role.get("staff_group"):  # a title's own staff group, granted at each club (owner, 2026-11-10)
            groups += [{"staff_group": {"id": "group-" + _slug(role["staff_group"]), "name": role["staff_group"]},
                        "scope_type": "venue", "scope": v} for v in venues]
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
