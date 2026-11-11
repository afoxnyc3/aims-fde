"""Recommend-only v1 contract for one JSM onboarding ticket.

The trusted adapter masks credentials and supplies source metadata. solve()
extracts onboarding details and proposes access from a versioned standard.
A caller posts the result to JSM; an associate reviews and provisions access.
Request has no fields for caller-supplied standards, production gates, or credentials.

The Request and Response types, with their field descriptions and validators,
live in models.py and are re-exported here.
"""

from __future__ import annotations

from models import (
    REVIEW_STATUSES,
    NamedReference,
    Recommendation,
    Request,
    Response,
    RoleAssignment,
    ScopeType,
    StaffGroupAssignment,
    Status,
    TicketComment,
)
from onboarding import recommend_access

__all__ = [
    "REVIEW_STATUSES",
    "NamedReference",
    "Recommendation",
    "Request",
    "Response",
    "RoleAssignment",
    "ScopeType",
    "StaffGroupAssignment",
    "Status",
    "TicketComment",
    "solve",
]


def solve(request: Request) -> Response:
    """Return a recommend-only access decision for one masked onboarding ticket.

    Extract onboarding details from free text; use a trusted, versioned role
    standard and native IDs. Ask for missing information, route ambiguity and
    exceptions to human review, and ignore unsupported tickets/roles. Earlier
    agent comments never constitute human approval. Expected operational errors
    return failed; invalid Request objects fail validation before this call,
    and unexpected programming errors propagate for debugging.

    The caller posts jira_comment only when present; ignored tickets receive no
    comment. This function does not provision accounts, issue credentials, or
    write to JSM or the account system. Production creation is a later gated phase.
    """
    return recommend_access(request)
