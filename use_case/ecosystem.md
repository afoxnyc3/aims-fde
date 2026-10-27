# The ecosystem you deploy into

Where your application would actually run, inside your actual firm.

> **Week 1 starts this file. Week 9 finishes it.**
> TC1 Step 10 asks eight questions. The full Week 9 checklist has around thirty,
> and the eight are a strict subset — so nothing here gets thrown away.

Describe patterns, not specifics. "On-prem OpenShift, images from an internal
registry, no public egress" is useful to everyone and identifies nobody. Never
put real hostnames, IPs, or architecture diagrams in this file.

---

## Week 1 — the first eight questions

<!-- Answered in TC1 Step 10. Bring these back from a real conversation. -->

**Who did you ask?** (role, not name)

Senior Systems Administrator about hosting (~2026-10-07); CTO about LLM access (2026-10-07). The hosting date is approximate. The deployment approver is known from my role as Senior Director, Technology (Head of IT. AWS and OpenRouter approval are known from my role. Azure Container Apps is the project owner’s selected service. Entra ID and Key Vault are confirmed from my Head of IT role; there is no internal registry, and the publishing path remains TBD. These are owner clarifications, not additional stakeholder conversations.

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

**Added 2026-10-18, outside the probe:** `registry.ollama.ai` (local model weights for TC2 Step 5) was reachable from this laptop. `qwen3:4b` and `qwen3:8b` pulled successfully through Ollama 0.40.6. The network it was on was not recorded, and the certificate signer was not checked.

**Recorded verdict:** Open network, public CAs, no proxy. Nothing here will bite you.

**Qualification:** Home-network results do not establish deployment access or rule out a proxy. Neither approved LLM provider was tested.

**Does this match what you were told in the table above?** Where it doesn't, that
gap is worth chasing — it usually means a proxy nobody documented.

Compare the home probe with [Azure egress verification](#azure-egress-verification); the two tests cover different environments.

### Egress — 2026-10-19 work laptop (Mac 1) / office network

Same probe (`helpers/preflight.py`), with three hosts added that the home run did not cover. The network is recorded as the office network on the project owner's statement; the tooling could not read the Wi-Fi name to confirm it.

| host | why | status | signed by |
| --- | --- | --- | --- |
| pypi.org | Python packages | OK | GlobalSign nv-sa |
| files.pythonhosted.org | the actual wheel downloads | OK | GlobalSign nv-sa |
| api.openai.com | the model API | OK | Google Trust Services |
| cdn.jsdelivr.net | the CDN the Week 1 frontend uses | OK | Sectigo Limited |
| huggingface.co | open weights, Weeks 2 and 8 | OK | Amazon |
| registry-1.docker.io | container images | OK | Amazon |
| github.com | this repository | OK | Sectigo Limited |
| api.anthropic.com | approved LLM provider | OK | Google Trust Services |
| openrouter.ai | approved LLM provider | OK | Google Trust Services |
| registry.ollama.ai | local model weights | OK | Google Trust Services |

**Probe verdict:** 10/10 reachable. Open network, public CAs, no proxy. No proxy environment variables and no macOS system proxy were set.

**End-to-end app check:** The Week 1 app ran locally with `uv run python app.py` (not in Docker). One synthetic message ("Connectivity test: reply with the single word OK.", no history, no ticket or member data) went to the `chat` endpoint at `localhost:7860`. The app called the Anthropic API with the configured `LLM_MODEL` and returned `OK` in about 1.3 s, with no errors in the app log. The app was then stopped.

**Qualification:** This verifies laptop egress and model access from the office network only. It does not verify Azure app-container egress, and OpenRouter was reached at the TLS level but not called with credentials.


### Azure egress verification

Separate test and production VNets use NAT gateways with the provisioned public IPs. The project owner queried `api.ipify.org` from all four VMs on October 12, 2026, and verified the expected outbound addresses. No addresses are published here.

The VMs are a governance and testing environment, separate from the container app: a Windows host runs the account-system client, and the Ubuntu hosts test the API while standards are established and automations are tested. The container app will egress through the same NAT gateways, so it uses the allowlisted addresses; its API credentials will come from Key Vault.

| Environment | Device | Result |
| --- | --- | --- |
| Test | Ubuntu VM | Expected outbound IP confirmed |
| Test | Windows VM | Expected outbound IP confirmed |
| Production | Ubuntu VM | Expected outbound IP confirmed |
| Production | Windows VM | Expected outbound IP confirmed |

#### Egress — 2026-10-19 Azure VMs

| Host | Why | Ubuntu TEST | Ubuntu PROD | Windows TEST | Windows PROD | Verified by |
| --- | --- | --- | --- | --- | --- | --- |
| api.anthropic.com | Anthropic API (auth verified, 200) | PASS | PASS | PASS | PASS | Project owner |
| openrouter.ai | OpenRouter model API (200) | PASS | PASS | PASS | PASS | Project owner |
| JSM site | Ticket intake, outbound status check (RUNNING) | PASS | PASS | PASS | PASS | Project owner |
| Account-system API (own environment) | Read access for onboarding agent; IP allowlist confirmed by Basic auth challenge | PASS | PASS | PASS | PASS | Project owner |
| Account-system API (other environment) | Isolation check; must be rejected | PASS (403) | PASS (403) | PASS (403) | PASS (403) | Project owner |

**Current status (2026-10-19):** Verified on all four VMs (Ubuntu and Windows, TEST and PROD). Each VM egresses directly through its VNet NAT IP, with no proxy. Certificate issuers for all external endpoints are public CAs (Google Trust Services, Amazon), so there is no TLS inspection on Azure egress. Each VM reaches only its own account-system environment, and TEST and PROD are isolated at the vendor IP allowlist. Authenticated account-system reads were tested from the Ubuntu TEST VM only; no writes were made in any environment.

Earlier history: test and production API tokens were received; API access requires an allowlisted IP plus credentials. The provider confirmed the allowlisting on 2026-10-14, and production API login and reads succeeded from Azure on 2026-10-16.

**Open:**
- Confirm least-privilege read roles on the account-system API accounts (tracked internally).
- Inbound JSM to Azure webhook is not yet verified.
- Container app egress is not yet verified (pending deployment).

This section is the source of access status; update it when confirmation or test results arrive.

---

## Project dependencies — supporting notes

Supporting dependencies; internal evidence stays separate. The input contract is in [CHARTER.md](CHARTER.md), with rationale in [decisions.md](decisions.md).

| Dependency | Required capability or decision | Status / next step | Role to consult |
| --- | --- | --- | --- |
| JSM onboarding intake | Complete readable ticket text, masking, source/author labels, and chronology | Confirm cloud vs. self-hosted JSM and webhook reachability; use polling or an approved relay if ingress is unavailable. Extraction stays inside `solve()` | Technology Support Associate / intake owner / Senior Systems Administrator |
| Input credential masking | Mask before model calls and logs; stop on errors or discovered misses | Confirm handling rules; defer contract tests to the Week 2 validator | Adapter implementer / security owner |
| Account-system API | Read access, create accounts, assign roles/permissions/venues, and verify results | Verify supported operations and write permissions; see [access status](#azure-egress-verification) | Senior Product Manager / Engineering |
| Upstream hire provisioning | Know where onboarding tickets originate relative to account creation | New hires flow from the HR system through an identity-provisioning tool into Entra; none of it is connected to Azure. Confirm the provisioning-to-Jira handoff before relying on the webhook trigger; paid support for the provisioning tool is approved pending budget, with new build work deferred | Senior Systems Administrator |
| Identity and role standard | Identity source, job-title mapping, permissions, venue add-ons, and login-email rules | Produce versioned drafts; confirm job levels, venue variation, and ratification owners | Product / role decision owners |
| Hosting | Container runtime, image publishing, authentication, and secrets | Azure Container Apps selected; hosting pattern validated by the Senior Systems Administrator (2026-10-16). App egress uses the existing NAT gateways; confirm registry and cost; see [egress evidence](#azure-egress-verification). Use the tested amd64 image and initially one replica; enable Entra sign-in and use Key Vault | Senior Systems Administrator / Senior Director of IT |
| Model access | Approved external LLM API | Anthropic available (CTO approval); the local Docker container called it successfully during Step 9, and the local app called it from the office network on 2026-10-19 (see [office egress](#egress--2026-10-19-work-laptop-mac-1--office-network)). All tests worked as designed; not blocked. Azure app-container connectivity is unverified. OpenRouter approved (known from my role). No internal endpoint | CTO / project owner |
| Embeddings (Week 3) | An embedding route for retrieval over ticket text | **Synthetic corpus only:** `openai/text-embedding-3-small` through OpenRouter (approved), measured 30,353 tokens for 116 pages on 2026-10-24. `nomic-embed-text` on local Ollama also answered the same probe. **Real ticket text (2026-10-27):** OpenRouter chosen for embeddings, since Anthropic's API has none; sending masked real ticket text to it needs the CTO and ISO sign-off for indexing real tickets, with the Senior Engineering Director's independent review (see [Week 3 — retrieval access scope](#week-3--retrieval-access-scope)). Until then the fallback is agentic BM25, which needs no embedding model and was measured (see [decisions](decisions.md), Week 3); the local model answered a probe but was never measured on the questions | CTO / security owner |
| Credential delivery | Unique credentials through an approved channel outside ticket comments | Confirm delivery and first-login behavior before production | Account-system owner / security owner |
| Production promotion | Ratified standard, write access, and 95% on synthetic tickets or 90% over at least 20 live tickets per role | CTO approves on reported results; set synthetic set size, coverage, and scoring rules (see [decisions](decisions.md)) | CTO / project owner / role decision owners |
| Course review | Demonstrate the onboarding workflow and evaluation within the course window | Confirm deliverable fit | Course team |

Conversations are recorded in [stakeholders.md](stakeholders.md). Build in test against draft standards while ratification proceeds. For the container app, keep production tokens only in Key Vault for the production runtime, never on laptops, in `.env` files, or in the test runtime; production writes remain gated per role. Offboarding stays out of scope.

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

## Week 3 — retrieval access scope

What the question endpoint would need to index real tickets. Drawn from two queries to the JSM configuration on 2026-10-27; the specifics (project key, request-type names, roles, tenant links) are kept in an internal note, not here. **The Jira admin still has to confirm the permission scheme.**

- **Source:** onboarding runs in a shared IT service desk project, not a dedicated one: about 520 onboarding tickets in the last 12 months. Promotions, transfers and title changes (about 100 a year) have no request type of their own: they arrive through the general service request, under a summary convention ("Promotion - …", "Status Change - …") and a structured description template. Software requests are not indexed: about 2% of them (around 20 a year) concern a new employee, and those are follow-ups to an onboarding ticket that is indexed.
- **Access is the whole project.** Jira grants Browse Projects per project, and nothing finer is configured for this one, so an account that can browse it can read every ticket in it, not only onboarding.
- **The service account:** read-only, in a dedicated project role rather than an existing one, so it can be audited and revoked on its own.
- **The indexing filter is the control.** It decides what is fetched, masked and stored. The project key and request-type values are local configuration, not committed. **Verified:** the field is `"Request Type"` with plain request-type names in double quotes (the `"Customer Request Type"` alias does not work in this tenant), and the onboarding clause returns the expected count. No label, component or custom field marks role changes today, so the interim filter reads the summary convention:

  ```
  project = $JSM_PROJECT AND (
    "Request Type" in ($ONBOARDING_REQUEST_TYPES)
    OR ("Request Type" in ($GENERAL_REQUEST_TYPES)
        AND (summary ~ "Promotion" OR summary ~ "\"Status Change\""))
  )
  ```

  **Measured:** the desk's two summary prefixes cover 98 of about 99 role changes in a year. The filter as written is a word match anywhere in the summary, not a prefix match (Jira text search stems words), so its own precision and recall must be measured before the first index. Matching the words "promotion" or "transfer" anywhere was precise (56 of 56 were role changes; no membership promotions or file transfers in this request type) but missed 43 status changes. A summary convention is a habit, not a control: **the design** is a dedicated role-change request type, since the desk already fills a structured template, which makes the filter exact. The indexer, when built, must stop on an empty clause, so a renamed request type cannot silently empty the index.
- **Attachments are not indexed** (see [decisions](decisions.md), Week 3 — non-text content): they are mostly signature icons, and ID or badge photos must never reach an external model.
- **Cost:** about 620 tickets a year at the synthetic pages' ~260 tokens each is roughly 160k embedding tokens a year. Add a one-off backfill of past years, and a full re-index that grows with the corpus (three years is about 500k). Estimates, since real tickets may run longer, but small at this volume.
- **Masking:** credentials are masked in the JSM adapter before indexing, per "Credential masking response" above. Planned, not built. That plan covers credentials only: whether names and personal emails are masked before ticket text reaches an external embedding route is open, and part of the sign-off. Masking names costs retrieval, since associates search by name. **Questions too:** hybrid retrieval embeds every associate's question through the same route at query time, unmasked, and questions name people. The sign-off covers both paths, or questions are embedded only after masking, or retrieval falls back to BM25.
- **Out of scope for now, with a recall risk:** a separate People Ops project also has an onboarding issue type. The Service Desk Manager's account of intake says promotions come from People Ops (stakeholders, 2026-10-20; open question 9). The role changes measured above were filed on the IT desk, but if some stay in the People Ops project the filter misses them, and the 98-of-99 figure would not show it. Ask People Ops.
- **Sign-off:** the CTO and the Information Security Officer approve indexing real tickets and the embedding route for ticket text and associates' questions. The acting ISO is also the project owner (Senior Director, Technology) who built this tool, so the Senior Engineering Director performs the independent review.

---

## Week 9 — the full checklist

<!--
  TC9 extends this same file. Do not start a new one: the point is that the git
  history shows one continuous piece of work from Week 1 to Week 9.
-->

<!-- Week 9 -->
