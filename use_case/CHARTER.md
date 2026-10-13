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
| Recommendation recorded on the ticket | 100% of recommendations posted before manual provisioning; baseline unmeasured |
| Tickets completed automatically | Report count and share of eligible live tickets for promoted roles |

The caller posts proposed roles and the standard version. Reconcile returned recommendations with JSM comments and report posted/returned counts. Zero recommendations means not assessed.

---

## The first product

**Your solution in one sentence.**

An agent that turns a JSM onboarding request into a verified account, recommending access changes until the role clears its production gate.

**Input → Output.** One call handles one ticket.

| | |
| --- | --- |
| **In** | A ticket reference, masked raw title/description/form text, and separate comments with trusted JSM author metadata and timestamps. Preserve all readable content and comment chronology; explicitly mark redacted and unavailable sections. No pre-parsed onboarding fields or caller-supplied standards/gates. |
| **Out** | **V1 recommends only:** `recommended`, `needs_information`, `human_review`, `ignored`, or `failed`. `answer=None` means no answer; uncertain recommendations carry caveats, not confidence scores. Exception reviews include an unapproved standard proposal and differences. The caller posts the comment when one is returned; ignored tickets get none. An associate provisions access. `solve()` performs no writes; credentials must be excluded, with output screening still to implement. |

The types and unimplemented `solve(request: Request) -> Response` are in [schema.py](../01_Product_Engineering/challenge/schema.py). V1 does not create accounts or write to JSM; gated production creation remains the later project end state.

The course-window deliverables include draft, versioned standards for scoped roles and the onboarding agent. Standards and gates come from trusted configuration. Build in test against drafts; production requires ratification. Deliver credentials through an approved channel outside ticket comments. Offboarding is out of scope.

---

## Decisions made later

Rationale and alternatives are recorded in [decisions.md](decisions.md); dependencies are in [ecosystem.md](ecosystem.md).

| Week | Decision |
| --- | --- |
| 3 | Proposed: exact lookup of the versioned role standard. |
| 5 | Direction set: ticket-triggered workflow, recommend first, then gated action. |
| 8 | Open: select the model using project evals. |
