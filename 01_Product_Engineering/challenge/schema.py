"""Recommend-only v1 contract for one JSM onboarding ticket.

The trusted adapter masks credentials and supplies source metadata. solve()
extracts onboarding details and proposes access from a versioned standard.
A caller posts the result to JSM; an associate reviews and provisions access.
Request has no fields for caller-supplied standards, production gates, or credentials.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Status(str, Enum):
    RECOMMENDED = "recommended"
    NEEDS_INFORMATION = "needs_information"
    HUMAN_REVIEW = "human_review"
    IGNORED = "ignored"
    FAILED = "failed"


class TicketComment(BaseModel):
    """Masked comment text with authorship supplied by trusted JSM metadata.

    Text cannot establish authorship. These fields must be populated by the
    authenticated adapter, not copied from labels a ticket author typed.
    """

    model_config = ConfigDict(extra="forbid")

    comment_id: str = Field(min_length=1)
    text: str = Field(description="Full credential-masked comment, without relevance filtering")
    created_at: datetime = Field(description="JSM timestamp, including timezone")
    author_type: Literal["agent", "human", "unknown"] = Field(
        description="Authorship from trusted adapter metadata, not comment text"
    )
    author_id: str | None = Field(default=None)

    @model_validator(mode="after")
    def _metadata_is_consistent(self) -> TicketComment:
        if self.author_type != "unknown" and not self.author_id:
            raise ValueError("known authorship requires a JSM author ID")
        if self.created_at.utcoffset() is None:
            raise ValueError("comment timestamps require a timezone")
        return self


class Request(BaseModel):
    """One masked ticket; onboarding extraction remains inside solve()."""

    model_config = ConfigDict(extra="forbid")

    ticket_ref: str = Field(min_length=1)
    ticket_text: str = Field(
        description=(
            "Full raw title, description, and all readable form questions/answers, "
            "labelled by source and credential-masked. Comments are supplied separately. "
            "No relevance filtering, silent truncation, or pre-parsed onboarding fields."
        )
    )
    comments: list[TicketComment] = Field(
        description="All readable comments in chronological order; explicitly [] if none"
    )
    redacted_sections: list[str] = Field(
        default_factory=list,
        description="Redacted source labels, including comment:<comment_id>; the only redaction metadata"
    )
    unavailable_sections: list[str] = Field(
        default_factory=list, description="Source sections the adapter could not read"
    )

    @model_validator(mode="after")
    def _comments_are_ordered(self) -> Request:
        times = [comment.created_at for comment in self.comments]
        if times != sorted(times):
            raise ValueError("comments must be in chronological order")
        return self


class NamedReference(BaseModel):
    """A native account-system identifier paired with its display name."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class ScopeType(str, Enum):
    SYSTEM = "system"
    BUSINESS_UNIT = "business_unit"
    VENUE = "venue"


class RoleAssignment(BaseModel):
    """A proposed role and its scope, both identified without name-only lookup."""

    model_config = ConfigDict(extra="forbid")

    role: NamedReference
    scope_type: ScopeType
    scope: NamedReference | None = Field(
        default=None, description="Required for business-unit and venue scope; absent for system"
    )

    @model_validator(mode="after")
    def _scope_is_consistent(self) -> RoleAssignment:
        if self.scope_type is ScopeType.SYSTEM and self.scope is not None:
            raise ValueError("system scope must not carry a venue or business unit")
        if self.scope_type is not ScopeType.SYSTEM and self.scope is None:
            raise ValueError("business-unit and venue assignments require a scope")
        return self


class StaffGroupAssignment(BaseModel):
    """An optional staff-group assignment using the same scope rules as roles."""

    model_config = ConfigDict(extra="forbid")

    staff_group: NamedReference
    scope_type: ScopeType
    scope: NamedReference | None = Field(default=None)

    @model_validator(mode="after")
    def _scope_is_consistent(self) -> StaffGroupAssignment:
        if self.scope_type is ScopeType.SYSTEM and self.scope is not None:
            raise ValueError("system scope must not carry a venue or business unit")
        if self.scope_type is not ScopeType.SYSTEM and self.scope is None:
            raise ValueError("business-unit and venue assignments require a scope")
        return self


class Recommendation(BaseModel):
    """Access changes an associate can apply without mirroring another user."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    person_name: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    start_date: date
    login_email: str = Field(
        min_length=1,
        description=(
            "Proposed using the standard's login rule; email availability and existing-account "
            "status are unchecked. The associate verifies both before provisioning; "
            "recommendations must not claim those checks were performed."
        ),
    )
    assignments: list[RoleAssignment] = Field(min_length=1)
    permissions: list[NamedReference] = Field(
        description="Independent permission grants; empty in the inherited-role-only demo. "
        "Effective permissions come from the assigned roles."
    )
    venues: list[NamedReference] = Field(
        min_length=1,
        description="Target account venues; venue-scoped assignments must reference these IDs/names",
    )
    standard_version: str = Field(min_length=1)
    proposed_changes: list[str] = Field(
        min_length=1, description="Exact provisioning steps; no credentials"
    )
    person_id: str | None = Field(default=None, description="Staff identifier, if available")
    matrix_entry_id: str | None = Field(
        default=None, description="Source row identifier within standard_version, if the standard has rows"
    )
    staff_groups: list[StaffGroupAssignment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _venues_are_consistent(self) -> Recommendation:
        venues = {venue.id: venue.name for venue in self.venues}
        if len(venues) != len(self.venues):
            raise ValueError("target venue IDs must be unique")
        for assignment in [*self.assignments, *self.staff_groups]:
            if assignment.scope_type is ScopeType.VENUE:
                scope = assignment.scope
                if scope is None or venues.get(scope.id) != scope.name:
                    raise ValueError("venue scopes must match a target venue ID and display name")
        return self


class Response(BaseModel):
    """An actionable recommendation or an explicit no-answer outcome.

    answer=None means no answer. Recommendations with caveats are shown with
    caution; v1 has no uncalibrated numeric confidence score. Ambiguity never
    produces a guessed answer. Exception reviews carry an unapproved standard
    proposal for comparison, separate from answer.

    Free-text fields can still contain secrets: descriptions and types do not
    enforce credential exclusion. Input masking and future output checks must
    cover this before production use; do not treat this schema as a secret scanner.
    """

    model_config = ConfigDict(extra="forbid")

    ticket_ref: str = Field(min_length=1)
    status: Status
    needs_human: bool = Field(description="Review required beyond applying a normal proposal")
    rationale: str = Field(min_length=1, description="Actionable explanation or no-answer reason")
    jira_comment: str | None = Field(
        default=None, min_length=1,
        description="Proposed internal comment; required except for ignored tickets; no credentials",
    )
    answer: Recommendation | None = Field(default=None)
    caveats: list[str] = Field(default_factory=list, description="Cautions accompanying an answer")
    missing_fields: list[str] = Field(default_factory=list)
    review_reason: Literal["ambiguous_identity", "ambiguous_mapping", "exception"] | None = None
    standard_proposal: Recommendation | None = Field(
        default=None, description="Unapproved standard baseline for exception review, never authorization"
    )
    exception_difference: list[str] = Field(default_factory=list)
    approval_owner_role: str | None = Field(
        default=None, description="Exception approver's role; None explicitly means unknown"
    )

    @model_validator(mode="after")
    def _status_is_consistent(self) -> Response:
        review_statuses = {Status.NEEDS_INFORMATION, Status.HUMAN_REVIEW, Status.FAILED}
        if self.needs_human != (self.status in review_statuses):
            raise ValueError("needs_human must agree with status")
        if self.status is Status.IGNORED:
            if self.jira_comment is not None:
                raise ValueError("ignored tickets must not receive a Jira comment")
        elif self.jira_comment is None:
            raise ValueError("non-ignored outcomes require an internal Jira comment")
        if self.status is Status.RECOMMENDED:
            if self.answer is None:
                raise ValueError("recommended requires an answer")
        elif self.answer is not None or self.caveats:
            raise ValueError("no-answer outcomes cannot carry an answer or answer caveats")
        if bool(self.missing_fields) != (self.status is Status.NEEDS_INFORMATION):
            raise ValueError("missing_fields is required only for needs_information")
        if (self.review_reason is not None) != (self.status is Status.HUMAN_REVIEW):
            raise ValueError("review_reason is required only for human_review")
        if self.review_reason == "exception":
            if self.standard_proposal is None or not self.exception_difference:
                raise ValueError("exception review requires a standard proposal and differences")
        elif (
            self.standard_proposal is not None
            or self.exception_difference
            or self.approval_owner_role is not None
        ):
            raise ValueError("standard proposal and exception details belong only to exception review")
        return self


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
    from onboarding import recommend_access

    return recommend_access(request)
