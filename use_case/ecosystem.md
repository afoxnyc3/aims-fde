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

Senior Systems Administrator about hosting; CTO about LLM access. Conversation dates are not recorded.

| # | Question | Answer |
| :---: | --- | --- |
| 1 | Where do internal apps run? (k8s, ECS, App Service, a VM someone maintains) | Azure container hosting, agreed with the Senior Systems Administrator. Specific service still to be confirmed. |
| 2 | Which cloud? AWS, Azure, GCP, on-prem, several? | Azure for this app; AWS is also approved. |
| 3 | Is there an internal container registry? | No internal Azure registry. Agree an image-publishing path with the Senior Systems Administrator: provision a managed registry or use an approved external registry. |
| 4 | How do users log in? (Okta, Entra ID, Ping, SAML, homegrown) | Entra ID. App-specific authentication setup remains to be confirmed. |
| 5 | Can the app reach the internet? Egress proxy? Allowlist? | Office and Azure runtime egress are untested; confirm proxy/allowlist requirements. Confirm JSM hosting and ingress: cloud webhooks need a reachable Azure endpoint; an internal-only endpoint would require polling or an approved relay. Existing results are from home. |
| 6 | Where do secrets come from? (Vault, Secrets Manager, Key Vault) | Azure Key Vault is planned for secrets. |
| 7 | Who approves a deployment, and what review does it need? | Senior Director of IT reviews and approves Azure deployments. Confirmation source and review criteria still need recording. |
| 8 | Is there an approved internal LLM endpoint already? | No internal LLM endpoint. Anthropic API is approved by the CTO and available; OpenRouter is also approved. |

**What surprised you?**

Azure hosting is agreed, but there is no internal container registry. The image-publishing path is unresolved: agree a managed registry or an approved external registry with the Senior Systems Administrator.

**What would you have to change about your app to deploy there?**

The Dockerfile already exists. Build for amd64 from the Mac; use a single replica initially, or session affinity if scaling. Move the key from `--env-file` to Key Vault and enable Entra sign-in. Confirm image publishing, JSM triggering, and Azure outbound access.

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

Not yet verifiable: office and Azure runtime egress are untested. Confirm policy and probe the deployment runtime. Record results without internal hostnames or IPs.

---

## Project dependencies — supporting notes

Supporting dependencies; internal evidence stays separate. The input contract is in [CHARTER.md](CHARTER.md), with rationale in [decisions.md](decisions.md).

| Dependency | Required capability or decision | Status / next step | Role to consult |
| --- | --- | --- | --- |
| JSM onboarding intake | Complete readable ticket text, masking, source/author labels, and chronology | Confirm cloud vs. self-hosted JSM and webhook reachability; use polling or an approved relay if ingress is unavailable. Extraction stays inside `solve()` | Technology Support Associate / intake owner / Senior Systems Administrator |
| Input credential masking | Mask before model calls and logs; stop on errors or discovered misses | Confirm handling rules; defer contract tests to the Week 2 validator | Adapter implementer / security owner |
| Account-system API | Read access, create accounts, assign roles/permissions/venues, and verify results | Confirm endpoints and separate test/production tokens; export fallback for inventory if needed | Engineering / system owner |
| Identity and role standard | Identity source, job-title mapping, permissions, venue add-ons, and login-email rules | Produce versioned drafts; confirm job levels, venue variation, and ratification owners | Product / role decision owners |
| Hosting | Container runtime, image publishing, authentication, and secrets | Confirm service and registry; build amd64, use one replica or session affinity, enable Entra sign-in, and use Key Vault | Senior Systems Administrator / Senior Director of IT |
| Model access | Approved external LLM API | No internal endpoint. Anthropic available; OpenRouter also approved | CTO |
| Credential delivery | Unique credentials through an approved channel outside ticket comments | Confirm delivery and first-login behavior before production | Account-system owner / security owner |
| Production promotion | Ratified standard, write access, and sufficient live accuracy per role | Confirm approver, scoring rules, and threshold | Project owner / role decision owners |
| Course review | Demonstrate the agent and evaluation within the course window | Confirm deliverable fit | Course team |

Conversations are recorded in [stakeholders.md](stakeholders.md). Build in test against draft standards while ratification proceeds. Offboarding stays out of scope.

## Credential masking response

Confirm the internal response owner and escalation route before production.

1. Mask in the JSM adapter before `solve()`, model calls, or trace/debug logging. Preserve surrounding text and redaction markers.
2. On masking errors or discovered misses, stop further calls and writes; route to human review without repeating the credential.
3. If already transmitted, follow the internal security-response process. Stopping later calls does not undo exposure.
4. Review the detector and obtain human clearance before retrying.

Masking can miss unknown secret formats; review detection coverage before production.

---

## Week 9 — the full checklist

<!--
  TC9 extends this same file. Do not start a new one: the point is that the git
  history shows one continuous piece of work from Week 1 to Week 9.
-->

<!-- Week 9 -->
