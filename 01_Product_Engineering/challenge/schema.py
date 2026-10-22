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


REVIEW_STATUSES = {Status.NEEDS_INFORMATION, Status.HUMAN_REVIEW, Status.FAILED}


class TicketComment(BaseModel):
    """Masked comment text with authorship supplied by trusted JSM metadata.

    Text cannot establish authorship. These fields must be populated by the
    authenticated adapter, not copied from labels a ticket author typed.
    """

    model_config = ConfigDict(extra="forbid")

    comment_id: str = Field(
        min_length=1,
        description=(
            "JSM's ID for this comment. Redacted comments are listed in redacted_sections "
            "as comment:<comment_id>."
        ),
    )
    text: str = Field(
        description=(
            "The comment's full text, with credentials masked. "
            "Must not be trimmed or filtered for relevance."
        )
    )
    created_at: datetime = Field(
        description="When the comment was posted, from JSM. Must include a timezone."
    )
    author_type: Literal["agent", "human", "unknown"] = Field(
        description=(
            "Who posted the comment: this app's automated agent, a person, or unknown. "
            "Comes from trusted JSM metadata, never from the comment text."
        )
    )
    author_id: str | None = Field(
        default=None,
        description="The author's JSM account ID. Required unless author_type is unknown.",
    )

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

    ticket_ref: str = Field(
        min_length=1, description="The JSM ticket key, such as DEMO-001. Copied into the response."
    )
    ticket_text: str = Field(
        description=(
            "The ticket's title, description, and every readable form question and answer, "
            "each labelled by source, with credentials masked. Sent whole: not filtered, "
            "truncated, or pre-parsed. Comments go in comments."
        )
    )
    comments: list[TicketComment] = Field(
        description=(
            "Every readable comment on the ticket, oldest first. "
            "An empty list means the ticket has no readable comments."
        )
    )
    redacted_sections: list[str] = Field(
        default_factory=list,
        description=(
            "Labels of the ticket sections that were redacted, such as description or "
            "comment:<comment_id>. The only place redactions are recorded; empty when nothing "
            "was redacted."
        ),
    )
    unavailable_sections: list[str] = Field(
        default_factory=list,
        description=(
            "Labels of the ticket sections the adapter couldn't read. "
            "Empty when every section was read."
        ),
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

    id: str = Field(min_length=1, description="The account system's ID for this item.")
    name: str = Field(min_length=1, description="The item's display name in the account system.")


class ScopeType(str, Enum):
    SYSTEM = "system"
    BUSINESS_UNIT = "business_unit"
    VENUE = "venue"


class RoleAssignment(BaseModel):
    """A proposed role and its scope, both identified without name-only lookup."""

    model_config = ConfigDict(extra="forbid")

    role: NamedReference = Field(description="The role to assign.")
    scope_type: ScopeType = Field(
        description="Where the role applies: the whole system, one business unit, or one venue."
    )
    scope: NamedReference | None = Field(
        default=None,
        description=(
            "The business unit or venue the role applies to. "
            "Must be null for system scope; required otherwise."
        ),
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

    staff_group: NamedReference = Field(description="The staff group to add the person to.")
    scope_type: ScopeType = Field(
        description="Where the membership applies: the whole system, one business unit, or one venue."
    )
    scope: NamedReference | None = Field(
        default=None,
        description=(
            "The business unit or venue the membership applies to. "
            "Must be null for system scope; required otherwise."
        ),
    )

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

    person_name: str = Field(min_length=1, description="The new hire's name, as given in the ticket.")
    job_title: str = Field(
        min_length=1,
        description=(
            "The job title exactly as written in the ticket, "
            "before it was matched to a standard role."
        ),
    )
    start_date: date = Field(description="The new hire's first day.")
    login_email: str = Field(
        min_length=1,
        description=(
            "The proposed login, built from the employee's email with the standard's login rule. "
            "Not checked for availability or an existing account; the associate verifies both, "
            "and the proposal must not claim otherwise."
        ),
    )
    assignments: list[RoleAssignment] = Field(
        min_length=1, description="The roles to assign, each with where it applies. Always at least one."
    )
    permissions: list[NamedReference] = Field(
        description=(
            "Permissions granted directly, on top of the roles. Effective permissions come from "
            "the assigned roles; empty when the standard grants nothing directly."
        )
    )
    venues: list[NamedReference] = Field(
        min_length=1,
        description=(
            "The venues the account needs access to. Every venue-scoped role or staff-group "
            "assignment must match one of these by ID and name."
        ),
    )
    standard_version: str = Field(
        min_length=1, description="The version of the access standard this proposal was built from."
    )
    proposed_changes: list[str] = Field(
        min_length=1,
        description="The provisioning steps for the associate, in order. Must not contain credentials.",
    )
    person_id: str | None = Field(
        default=None,
        description="The person's existing account-system ID, if the ticket gives one; null otherwise.",
    )
    matrix_entry_id: str | None = Field(
        default=None,
        description=(
            "The ID of the access-standard row that matched the job title. "
            "Null if the standard has no rows."
        ),
    )
    staff_groups: list[StaffGroupAssignment] = Field(
        default_factory=list,
        description=(
            "Staff groups to add the person to, each with where it applies. "
            "Empty when the role needs none."
        ),
    )

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

    ticket_ref: str = Field(
        min_length=1, description="The ticket this response is for, copied from the request."
    )
    status: Status = Field(
        description="The outcome: recommended, needs_information, human_review, ignored, or failed."
    )
    needs_human: bool = Field(
        description=(
            "True when a person must resolve the ticket before any proposal can be applied: "
            "needs_information, human_review, or failed. A recommended proposal is still checked "
            "and applied by an associate. Always follows from status."
        )
    )
    rationale: str = Field(
        min_length=1,
        description=(
            "A short, actionable explanation of the outcome: what is proposed, "
            "or why there is no proposal."
        ),
    )
    jira_comment: str | None = Field(
        default=None, min_length=1,
        description=(
            "The internal comment to post on the ticket. Required for every status except "
            "ignored, where it must be null. Must not contain credentials."
        ),
    )
    answer: Recommendation | None = Field(
        default=None,
        description="The proposed access. Required when status is recommended; null otherwise.",
    )
    caveats: list[str] = Field(
        default_factory=list,
        description=(
            "Points the associate should check before applying the answer. "
            "Allowed only when status is recommended; empty otherwise."
        ),
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description=(
            "Names of the ticket facts to ask the requester for, such as job_title or "
            "employee_email. Required when status is needs_information; empty otherwise."
        ),
    )
    review_reason: Literal["ambiguous_identity", "ambiguous_mapping", "exception"] | None = Field(
        default=None,
        description=(
            "Why a person needs to review the ticket: conflicting identities, a mixed job title "
            "or a unit or venue that can't be mapped to the standard, or a request for access "
            "beyond the standard. Required when status is human_review; null otherwise."
        ),
    )
    standard_proposal: Recommendation | None = Field(
        default=None,
        description=(
            "What the standard alone would propose, for comparison. Required for exception "
            "reviews; null otherwise. Not an approval, and never authorizes an access change."
        ),
    )
    exception_difference: list[str] = Field(
        default_factory=list,
        description=(
            "The access requested beyond the standard. Required for exception reviews; "
            "empty otherwise."
        ),
    )
    approval_owner_role: str | None = Field(
        default=None,
        description=(
            "For exception reviews: the role that can approve the exception, or null if unknown. "
            "Must be null for every other outcome."
        ),
    )

    @model_validator(mode="after")
    def _needs_human_matches_status(self) -> Response:
        """Statuses that hand work to a person must say so; the others must not."""
        if self.needs_human != (self.status in REVIEW_STATUSES):
            raise ValueError("needs_human must agree with status")
        return self

    @model_validator(mode="after")
    def _jira_comment_matches_status(self) -> Response:
        """Ignored tickets get no Jira comment; every other outcome gets one."""
        if (self.jira_comment is None) != (self.status is Status.IGNORED):
            raise ValueError("ignored tickets get no Jira comment; all other outcomes need one")
        return self

    @model_validator(mode="after")
    def _answer_matches_status(self) -> Response:
        """Only a recommendation carries an answer, and caveats only accompany an answer."""
        if self.status is Status.RECOMMENDED:
            if self.answer is None:
                raise ValueError("recommended requires an answer")
        elif self.answer is not None or self.caveats:
            raise ValueError("no-answer outcomes cannot carry an answer or answer caveats")
        return self

    @model_validator(mode="after")
    def _missing_fields_match_status(self) -> Response:
        """missing_fields is filled exactly when the ticket needs more information."""
        if bool(self.missing_fields) != (self.status is Status.NEEDS_INFORMATION):
            raise ValueError("missing_fields is required only for needs_information")
        return self

    @model_validator(mode="after")
    def _review_reason_matches_status(self) -> Response:
        """review_reason is set exactly when the ticket goes to human review."""
        if (self.review_reason is not None) != (self.status is Status.HUMAN_REVIEW):
            raise ValueError("review_reason is required only for human_review")
        return self

    @model_validator(mode="after")
    def _exception_details_match_reason(self) -> Response:
        """Exception reviews carry the standard baseline and the differences; nothing else does."""
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
