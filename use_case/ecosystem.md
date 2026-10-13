# Someone else's ecosystem

Where your application would actually run, inside your actual firm.

> **Week 1 starts this file. Week 9 finishes it.**
> TC1 Step 6 asks eight questions. The full Week 9 checklist has around thirty,
> and the eight are a strict subset — so nothing here gets thrown away.

Describe patterns, not specifics. "On-prem OpenShift, images from an internal
registry, no public egress" is useful to everyone and identifies nobody. Never
put real hostnames, IPs, or architecture diagrams in this file.

---

## Week 1 — the first eight questions

<!-- Answered in TC1 Step 6. Bring these back from a real conversation. -->

**Who did you ask?** (role, not name)

Senior Systems Administrator about hosting (~2026-10-07); CTO about LLM access (2026-10-07). The hosting date is approximate. The deployment approver is known from my role as Senior Director / Head of IT. AWS and OpenRouter approval are known from my role. Azure Container Apps is the project owner’s selected service. Entra ID and Key Vault are confirmed from my Head of IT role; there is no internal registry, and the publishing path remains TBD. These are owner clarifications, not additional stakeholder conversations.

| # | Question | Answer |
| :---: | --- | --- |
| 1 | Where do internal apps run? (k8s, ECS, App Service, a VM someone maintains) | Azure Container Apps, selected by the project owner following the Azure hosting discussion with the Senior Systems Administrator. |
| 2 | Which cloud? AWS, Azure, GCP, on-prem, several? | Azure for this app; AWS is also approved, known from my Head of IT role. |
| 3 | Is there an internal container registry? | No internal Azure registry. Agree an image-publishing path with the Senior Systems Administrator: provision a managed registry or use an approved external registry. |
| 4 | How do users log in? (Okta, Entra ID, Ping, SAML, homegrown) | Entra ID, confirmed from my Head of IT role. App-specific sign-in integration remains to be configured. |
| 5 | Can the app reach the internet? Egress proxy? Allowlist? | See [Azure egress verification](#azure-egress-verification) for tested paths and API-access status. Confirm JSM webhook reachability; otherwise use polling or an approved relay. |
| 6 | Where do secrets come from? (Vault, Secrets Manager, Key Vault) | Azure Key Vault, confirmed from my Head of IT role. App integration remains pending. |
| 7 | Who approves a deployment, and what review does it need? | The project owner approves Azure deployments as Senior Director / Head of IT (known from my role). Independent review and deployment criteria remain to be agreed; see [planned conversations](stakeholders.md#conversations-to-arrange). |
| 8 | Is there an approved internal LLM endpoint already? | No internal LLM endpoint. Anthropic API is approved by the CTO and available; OpenRouter approval is known from my Head of IT role. |

**What surprised you?**

Azure Container Apps is selected, but there is no internal container registry; the image-publishing path remains unresolved. Agree a managed registry or an approved external registry with the Senior Systems Administrator.

**What would you have to change about your app to deploy there?**

The amd64 image is built and tested locally. Configure Azure Container Apps and agree the image-publishing path; use a single replica initially, or validate queue/session routing before scaling. Move the model key from `--env-file` to Key Vault, enable Entra sign-in, and pin and bundle the browser client. Confirm JSM triggering, app-container egress, and independent review before deployment.

---

## Week 1 — what your machine told you

### Egress — 2026-10-08 work laptop (Mac 1) / home network

| host | why | status | signed by |
| --- | --- | --- | --- |
| pypi.org | Python packages | OK | GlobalSign nv-sa |
| files.pythonhosted.org | the actual wheel downloads | OK | GlobalSign nv-sa |
| api.openai.com | the model API | OK | Google Trust Services |
| cdn.jsdelivr.net | the CDN the Week 1 frontend uses | OK | Sectigo Limited |
| huggingface.co | open weights, Weeks 2 and 8 | OK | Amazon |
| registry-1.docker.io | container images | OK | Amazon |
| github.com | this repository | OK | Sectigo Limited |

**Recorded verdict:** Open network, public CAs, no proxy. Nothing here will bite you.

**Qualification:** Home-network results do not establish deployment access or rule out a proxy. Neither approved LLM provider was tested.

**Does this match what you were told in the table above?** Where it doesn't, that
gap is worth chasing — it usually means a proxy nobody documented.

Compare the home probe with [Azure egress verification](#azure-egress-verification); the two tests cover different environments.


### Azure egress verification

Separate test and production VNets use NAT gateways with the provisioned public IPs. The project owner queried `api.ipify.org` from all four VMs on October 12, 2026, and verified the expected outbound addresses. No addresses are published here.

| Environment | Device | Result |
| --- | --- | --- |
| Test | Ubuntu VM | Expected outbound IP confirmed |
| Test | Windows VM | Expected outbound IP confirmed |
| Production | Ubuntu VM | Expected outbound IP confirmed |
| Production | Windows VM | Expected outbound IP confirmed |

**Current status:** Test and production API tokens are received. These were outbound-IP checks, not account-system API calls. API tests can proceed through the already-allowlisted office/VPN connection. The provider has not updated the Azure allowlist request; Azure API access, app-container egress, and write permissions remain unverified.

This section is the source of access status; update it when confirmation or test results arrive.

---

## Project dependencies — supporting notes

Supporting dependencies; internal evidence stays separate. The input contract is in [CHARTER.md](CHARTER.md), with rationale in [decisions.md](decisions.md).

| Dependency | Required capability or decision | Status / next step | Role to consult |
| --- | --- | --- | --- |
| JSM onboarding intake | Complete readable ticket text, masking, source/author labels, and chronology | Confirm cloud vs. self-hosted JSM and webhook reachability; use polling or an approved relay if ingress is unavailable. Extraction stays inside `solve()` | Technology Support Associate / intake owner / Senior Systems Administrator |
| Input credential masking | Mask before model calls and logs; stop on errors or discovered misses | Confirm handling rules; defer contract tests to the Week 2 validator | Adapter implementer / security owner |
| Account-system API | Read access, create accounts, assign roles/permissions/venues, and verify results | Verify supported operations and write permissions; see [access status](#azure-egress-verification) | Senior Product Manager / Engineering |
| Identity and role standard | Identity source, job-title mapping, permissions, venue add-ons, and login-email rules | Produce versioned drafts; confirm job levels, venue variation, and ratification owners | Product / role decision owners |
| Hosting | Container runtime, image publishing, authentication, and secrets | Azure Container Apps selected; confirm registry, app-container routing, and cost; see [egress evidence](#azure-egress-verification). Use the tested amd64 image and initially one replica; enable Entra sign-in and use Key Vault | Senior Systems Administrator / Senior Director of IT |
| Model access | Approved external LLM API | Anthropic available (CTO approval); the local Docker container called it successfully during Step 9. Azure app-container connectivity is unverified. OpenRouter approved (known from my role). No internal endpoint | CTO / project owner |
| Credential delivery | Unique credentials through an approved channel outside ticket comments | Confirm delivery and first-login behavior before production | Account-system owner / security owner |
| Production promotion | Ratified standard, write access, and sufficient live accuracy per role | Confirm approver, scoring rules, and threshold | Project owner / role decision owners |
| Course review | Demonstrate the onboarding workflow and evaluation within the course window | Confirm deliverable fit | Course team |

Conversations are recorded in [stakeholders.md](stakeholders.md). Build in test against draft standards while ratification proceeds. Keep production tokens only in Key Vault for the production runtime, never on laptops, in `.env` files, or in the test runtime; production writes remain gated per role. Offboarding stays out of scope.

## Credential masking response

Confirm the internal response owner and escalation route before production.

1. Mask in the JSM adapter before `solve()`, model calls, or trace/debug logging. Preserve surrounding text and redaction markers.
2. On masking errors or discovered misses, stop further calls and writes; route to human review without repeating the credential.
3. If already transmitted, follow the internal security-response process. Stopping later calls does not undo exposure.
4. Review the detector and obtain human clearance before retrying.

Masking can miss unknown secret formats; review detection coverage before production.

---

## Week 1 — local container verification

Docker Desktop built and ran the application on October 13, 2026. The Mac is arm64; the image targets linux/amd64 for Azure and ran locally under emulation. No alternate container runtime was needed. `/health` and a synthetic golden through the browser form passed; see [Step 9 verification](README.md#step-9--container-deployment). This does not verify Azure deployment or account-system API access.

---

## Week 9 — the full checklist

<!--
  TC9 extends this same file. Do not start a new one: the point is that the git
  history shows one continuous piece of work from Week 1 to Week 9.
-->

<!-- Week 9 -->
