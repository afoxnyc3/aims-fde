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
