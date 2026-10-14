# Stakeholders

Everyone you talk to about this project, from the first "where would this even
run?" to the final readout.

> **Week 10's technical challenge is a client report to the people in this file.**
> You cannot write it later from memory. Add a row the day you have the
> conversation.

Use roles, not names. This is a public fork.

Product Manager and CTO dates are confirmed; the remaining dates are approximate.

| Week / date | Who (role) | What you asked | What you learned | Follow-up |
| --- | --- | --- | --- | --- |
| 1 / 2026-10-07 | CTO | Discussed targeting roles covering 80% of onboarding effort and LLM API access. | Endorsed the 80% approach. Anthropic API is approved and available. | Validate effort-based scope and review project outcomes. |
| 1 / ~2026-10-07 | Senior Systems Administrator | Discussed Azure hosting using a container service. | Agreed to Azure container hosting. | Review the selected Azure Container Apps deployment, registry, JSM ingress, app-container routing through the tested NAT gateways, approved model connectivity, and cost. |
| 1 / ~2026-10-08 | Technology Support Associate | Discussed onboarding pain points and observed several tickets being completed. | Missing role governance drives lookups of users at the same venue or in the same role elsewhere to decide whose access to mirror. | Demo the standard and ticket comment. Ask “What would you use this for?” before explaining; collect candid written feedback on remaining lookups and gaps. |
| Pre-course + week 2 / 2026-10-05, 2026-10-12 | Senior Product Manager | Discussed roles, permissions, governance, and agent-based onboarding automation. | Oversees Fitness and the club-management application. Provided test and production API tokens. | Verify API operations and write permissions using the paths in [access status](ecosystem.md#azure-egress-verification). Demo the endpoint and roadmap; identify role-standard ratifiers. |

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

- Role-standard owners: identify the department heads who will ratify permissions and agree a review date with Product.
- Security owner: confirm credential masking, delivery, and the independent review for a deployment built by its approver.

The project owner is the Senior Director / Head of IT and deployment approver. This is context, not a stakeholder conversation. Owner clarification (2026-10-13): Azure Container Apps is selected; Entra ID and Key Vault are confirmed from that role. There is no internal registry; the image-publishing path remains TBD.
