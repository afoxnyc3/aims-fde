# Stakeholders

Everyone you talk to about this project, from the first "where would this even
run?" to the final readout.

> **Week 10's technical challenge is a report to the people in this file.**
> You cannot write it later from memory. Add a row the day you have the
> conversation.

Use roles, not names. This is a public repo.

Product Manager and CTO dates are confirmed; the remaining dates are approximate.

| Week / date | Who (role) | What you asked | What you learned | Follow-up |
| --- | --- | --- | --- | --- |
| 1 / 2026-10-07 | CTO | Discussed targeting roles covering 80% of onboarding effort and LLM API access. | Endorsed the 80% approach. Anthropic API is approved and available. | Validate effort-based scope and review project outcomes. |
| 1 / ~2026-10-07 | Senior Systems Administrator | Discussed Azure hosting using a container service. | Agreed to Azure container hosting. | Review the selected Azure Container Apps deployment, registry, JSM ingress, app-container routing through the tested NAT gateways, approved model connectivity, and cost. |
| 1 / ~2026-10-08 | Technology Support Associate | Discussed onboarding pain points and observed several tickets being completed. | Missing role governance drives lookups of users at the same venue or in the same role elsewhere to decide whose access to mirror. | Demo the standard and ticket comment. Ask “What would you use this for?” before explaining; collect candid written feedback on remaining lookups and gaps. |
| Pre-course + week 2 / 2026-10-05, 2026-10-12 | Senior Product Manager | Discussed roles, permissions, governance, and agent-based onboarding automation. | Oversees Fitness and the club-management application. Provided test and production API tokens. | Verify API operations and write permissions using the paths in [access status](ecosystem.md#azure-egress-verification). Demo the endpoint and roadmap; identify role-standard ratifiers. |
| 2 / 2026-10-15 | CTO | Demoed the onboarding workflow and the role-governance case. | Positive reception. Set the promotion gate at 95% accuracy on synthetic tickets, replacing the proposed 90% over 20 live tickets: once ratified, a standard is a lookup table, and live-only evidence could take months per role. The CTO will sign off promotions on reported data. Named role-standard ratifiers. Recommended limiting the Admin role to Tech and Finance. Asked whether names can be validated against the HR system, whether lookups stem from bad source data, about OpenRouter for provider agnosticism, and whether submitters are notified of Needs Information. | Export all roles and assignments, and user logs to confirm which permissions are used. Build the synthetic ticket set for the 95% gate. Obtain the VP Hospitality's SOPs. Make the cybersecurity case for the Admin restriction. |
| 2 / 2026-10-16 | Senior Systems Administrator | Architecture walkthrough: Jira and account-system integration scope, data sources, compute choice, account scope, and the upstream onboarding handoff. | Validated the hosting pattern (project in Azure, credentials in Key Vault) as matching prior team work. The HR system and Entra are not connected to anything in Azure; all HR onboardings flow through an identity-provisioning tool. Approved paid support for that tool, pending budget; new build work is deferred until this year's commitments clear. Values the visibility that scheduling and logs give into onboarding work. | Confirm the current provisioning-to-Jira handoff. Investigate pushing provisioning notifications into Jira and sending temporary passwords to managers. Agree the scope of the production write credential. |
| 2 / 2026-10-19 | Technology Support Associate (Service Desk, works the onboarding queue) | Blind read of 20 synthetic tickets ("Would this ever happen? What would you do?"), then the seven open policy questions with our labels shown. | Judged 16 of 20 realistic; tickets 8, 11 and both fixed rows (17, 18) unrealistic. Accepted both planted oddities (19, 20) as realistic. Stated answers, none with a named decider, so none ratified: Q7 treat a login disagreement as a contradiction and ask the requester; Q2 send for review first; Q5 same access at every level; Q1 recommend with a note to check the existing account; Q6 one rule per role everywhere; Q3 not decided; Q4 requester or listed manager only. Practice in the blind read differed from the stated answer on Q7 (processed 2, 3, 4 and 13; on 12, "login created as part of the role and job requirement") and Q2 (on 9, "membership only no login"). On 16 they would "create account according to start date and mirror access". On 5 they would move venues and drop the extra request ("no tablet"). | Asked the two Step 6 questions the session did not cover (what comes in that isn't here; what would worry them if public) by Teams on 2026-10-20. Reconcile Q7 and Q2 stated policy with practice, with a named decider. Send Q5 and Q6 to the VP Hospitality. Take Q4 to the security owner. |
| 2 / 2026-10-19 | Senior Product Manager | Meeting on the club-management API and the Fitness roles. | Two complaints. The account-system API has no endpoints to create staff groups or roles; they can only be assigned, so any staff group or role a standard needs must already exist or be created by hand. There is no clear definition of what changes between Fitness Trainer levels 1–4: nothing is documented in Confluence, and the PM does not know what varies in duties or permissions. | Decide who creates missing staff groups and roles, and when (see [decisions still required](decisions.md#decisions-still-required)). Take trainer levels (open question 5) to the Fitness leads. |
| 2 / 2026-10-20 | Service Desk Manager | Which onboarding form each part of the business uses, to check whether the synthetic tickets' blank fields are realistic. | The fitness business unit files onboarding through the HR intake form ("Employee Updates and Requests"); all other business units use the service portal's onboarding form. The two forms require different fields, so required-field rules from the portal form do not apply to the fitness tickets v1 models. Confirmed by Teams the same day: on the fitness form, the requester is always the hiring manager. Later answers: managers file offboarding, transfers and promotions; Target Date on the fitness form is the start date (required); the form's position title syncs to the ticket's job title field; all other support requests (IT help, outages, changes) come through Jira. | Asked: which fields appear, and which are required, when the HR intake form's new-hire topic is chosen (decides whether a blank job title, start date or location is realistic); and which form IT help, outage, permission-change and offboarding requests use (decides fixed row #45). |
| 2 / 2026-10-20 | Technology Support Associate (Service Desk, works the onboarding queue) | Follow-up by Teams: the two Step 6 questions the 10/19 session did not cover. | What comes in that isn't here: Babysitting Associate and Babysitting Lead, with access similar to Hospitality Associate. If this were public, what would worry you: read as the intake form being open to anyone; "only managers should be able to submit onboarding requests; others submitting information may cause issues during onboarding." Shared People Ops' role-by-access matrix (dated 2026-10-07; internal, kept out of this repo). Their account of intake differs from the Service Desk Manager's: offboarding and promotions come from People Ops. | Ask People Ops whether the role matrix is current and who ratifies it. Reconcile who files offboarding and promotions (open question 9). |
| 2 / 2026-10-20 | Technology Support Associate (staff-login check page) | For each of 9 roles in the draft standard: does a new hire get a staff login? (Yes / No / Depends on club / Not sure.) | Seven of nine match the draft standard and People Ops' role matrix: Group Fitness Instructor, Personal Trainer, Front Desk Associate, Massage Therapist and Membership Consultant yes; Cafe Associate and Housekeeping Associate no. Lifeguard and Aquatics Lead: depends on club, at two named clubs only. The matrix says yes with no club distinction, and the draft venue table says by club, but for different clubs. | Confirm whether those two clubs are the only ones with pools; if so, the rule is "always, where the role exists", not a by-club login rule. The same check is out with the Senior Product Manager. |

---

## Not everyone is an infrastructure contact

The useful list is wider than it first looks, and Week 10's report goes to all of
them:

- **The person with the problem** — the one from your charter. Have you shown
  them anything yet?
- **Whoever owns the data** you would need.
- **Whoever runs the platform** your app would deploy onto.
- **Whoever approves** a deployment, a spend, or a vendor.
- **Your own manager**, who will be asked whether this was worth the ten weeks.

If a week goes by with no conversation, add a row saying so and why. A visible
gap is more useful than a silent one.

## Conversations to arrange

- Role-standard owners, named by the CTO (2026-10-15); agree a review date with Product:
  - VP Sales: sales roles.
  - VP Hospitality: Member Services, Concierge, and Front Desk; has drafted SOPs for several roles.
  - Fitness leads (three): fitness roles.
- Talk with the VP Finance about prior consulting on the second region.
- HR system owner: whether new-hire names can be validated against the HR system.
- Service Desk Manager (manages the Technology Support Associates): ownership of post-automation audits, verification sampling, and revert decisions.
- Security owner: confirm credential masking, delivery, and the independent review for a deployment built by its approver.

The project owner is the Senior Director / Head of IT and deployment approver. This is context, not a stakeholder conversation. Owner clarification (2026-10-13): Azure Container Apps is selected; Entra ID and Key Vault are confirmed from that role. There is no internal registry; the image-publishing path remains TBD.
