# Project charter

**Department:** IT Operations, Service Desk

**Working title:** Onboarding Access for the 80%

**Scope:** Workplace project developed during an FDE course, October–December 2026. Company evidence stays internal.

---

## The problem

**Who has it?**

Technology Support Associates handling onboarding tickets in Jira Service Management (JSM).

**What are they trying to do?**

Create a new hire's club-management account with the correct roles, permissions, and venue access.

**How do they handle it today?**

They combine tribal knowledge, documentation, comparisons with existing users, and department-head decisions. Permissions vary within and across venues without a consistently governed standard.

**What does that cost — time, money, risk, or relationships?**

Inconsistent decisions risk inappropriate access and make onboarding dependent on others' availability. Internal analysis estimates that coordination is 17% of tickets but 46% of effort. Monthly onboarding volume rose about 50% between the year's first and second halves; median calendar resolution time rose about 37% after an operational handover. Effort is estimated; calendar delay is not handling time.

**The problem in one sentence. No solution in it.**

A Technology Support Associate cannot reliably determine a new hire's club-management permissions from their role and venue because existing access varies, forcing repeated lookup and coordination on onboarding tickets.

---

## Success

**What does the new world look like for that person?**

The Technology Support Associate can apply the proposed access from the ticket comment without looking up other users or emailing to establish standard access. For promoted roles, the agent creates the account, verifies access, and records the result; the associate handles exceptions and spot-checks results. Rollout starts with recommendations, then acts per role after approval, API access, and accuracy gates clear. Scope targets roles covering 80% of onboarding effort; coverage remains unvalidated.

**How would the firm measure it? Which numbers should move?**

| Measure | Target |
| --- | --- |
| Associate handling minutes per scoped ticket | Reduce; set target after measuring baseline |
| Replayed proposals matching the standard | At least 90%, proposed |
| Granted role recorded on the ticket | Baseline 0%; target 100% of project-processed onboarding tickets |
| Tickets completed automatically | Report count and share of eligible live tickets for promoted roles |

---

## The first product

**Your solution in one sentence.**

An agent that turns a JSM onboarding request into a verified account, recommending access changes until the role clears its production gate.

**Input → Output.** One call handles one ticket.

| | |
| --- | --- |
| **In** | `solve()` receives a ticket reference and credential-masked raw ticket text: the full title, description, all form questions/answers, and all comments readable by the JSM adapter, labelled by source and ordered chronologically for comments. Comment labels include author ID, timestamp, and whether the author is the agent, derived from JSM metadata. No content is selected by relevance or silently truncated; redactions and unavailable sections are marked. The agent extracts person, job title, venues, start date, and exceptions; callers do not supply pre-parsed onboarding fields. |
| **Out** | Ticket reference and status: recommended, completed, needs information, human review, ignored, or failed. Resolved roles, permissions, and venues use account-system IDs plus display names; include standard version and proposed changes. Missing fields produce needs information; ambiguous identities/mappings or exceptions produce human review, with the difference from the standard and approval-owner role for exceptions. Unsupported ticket types/roles are ignored; execution errors are failed. Completion includes account ID and verified access. Record the outcome on the ticket; return no credentials. |

The course-window deliverables include draft, versioned standards for scoped roles and the onboarding agent. Standards and gates come from trusted configuration. Build in test against drafts; production requires ratification. Deliver credentials through an approved channel outside ticket comments. Offboarding is out of scope.

---

## Decisions made later

Rationale and alternatives are recorded in [decisions.md](decisions.md); dependencies are in [ecosystem.md](ecosystem.md).

| Week | Decision |
| --- | --- |
| 3 | Proposed: exact lookup of the versioned role standard. |
| 5 | Direction set: ticket-triggered workflow, recommend first, then gated action. |
| 8 | Open: select the model using project evals. |
