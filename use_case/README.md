# Your use case

**This directory is yours.** Everything else in this repository is teaching
material we wrote. This is the one place you work, and every technical challenge
across all ten weeks reads from it or writes to it.

> **One use case, all ten weeks, no restarts.**

That rule is the whole design. The most common way this cohort goes wrong is a
student switching use cases in Week 5 because the first one got hard — and then
Week 8 has nothing to fine-tune against and Week 10 has nobody to report to.
Choose something you actually own, at work, that annoys you weekly.

---

## The files

| File | Created in | Grows in | Collected in |
| --- | --- | --- | --- |
| [`CHARTER.md`](./CHARTER.md) | TC1 | TC3, TC5, TC8 | every week's Session 2 opens by reading it |
| [`stakeholders.md`](./stakeholders.md) | TC1 Step 6 | **every week** | **TC10** — the final report goes to these people |
| [`ecosystem.md`](./ecosystem.md) | TC1 Step 6 | **TC9** extends this same file | TC9, TC10 |
| [`decisions.md`](./decisions.md) | TC3 | TC5–TC8 | TC5's critique, TC10's handoff doc |
| [`evals/golden.jsonl`](./evals/) | Week 1 S2 | TC2, TC4, TC6 | **TC8** — the bar a fine-tuned model must clear |
| [`data/DATASHEET.md`](./data/DATASHEET.md) | TC2 | TC3, TC8 | reviewers |
| `app/` | TC1 | TC3, TC5–TC8 | TC10 handoff |

Nothing here is busywork. Each file exists because something later is impossible
without it. `stakeholders.md` is the clearest case: TC10 asks you to send a
client report to everyone you worked with during the cohort. If you did not keep
the log, you cannot write the report.

---

## 🔒 Never commit real company data

`data/` is gitignored except its datasheet. That is deliberate and it is not
negotiable — you are pushing this to a public fork.

| Don't commit | Do commit |
| --- | --- |
| Real records, tickets, documents, customer names | Synthetic data you generated |
| Internal hostnames, IPs, architecture diagrams | The *shape* of the answer: "on-prem k8s, SAML, no egress" |
| Credentials, tokens, connection strings | `.env.example` with placeholders |
| Screenshots of internal tools | Screenshots of your own app |

When describing your firm's infrastructure, describe the pattern, not the
specifics. "Images go to an internal registry; Docker Hub is blocked" is useful
to everyone and identifies nobody.

If in doubt, leave it out.


## Step 7 — golden examples

Edge case: DEMO-002 (a note replaces the trainer level); decline: DEMO-003 (ambiguous role mapping and a peer-mirroring request).


## Step 8 — endpoint design

- **Work it takes over:** interpreting an onboarding ticket and proposing standard access, without copying another user's permissions. The associate checks existing accounts and provisions access.
- **Input:** `onboarding_ticket_json`, serialized Request data with ticket_ref, masked ticket_text, and chronological comments carrying trusted metadata; optional redaction and unavailable-section markers.
- **Output and reader:** validated Response JSON for the Technology Support Associate: a recommendation, missing information, review outcome, ignored ticket, or operational failure. Ignored tickets return no proposed comment.
- **Name:** `recommend_onboarding_access`; it names the work and signals recommendations rather than account creation.

The UI displays structured results and distinguishes invalid input from failed processing. The implemented solve() returns standard-backed recommendations and explicit no-answer outcomes; it is no longer a stub. Authentication, databases, and live JSM/account-system writes remain outside this week's build.


### Running the Step 8 demo

From `01_Product_Engineering/challenge/`, run `uv run --env-file .env python app.py` and open `http://localhost:7860`. The `.env` file is for the approved model configuration only; no production account-system tokens belong there. Paste a golden's `input` object into the onboarding form. General chat remains available below it.

The model extracts facts; code performs lookup and constructs access from `demo_standard.json`. It never reads golden outputs at runtime. The UI is a synthetic, masked-input demo, not a production JSM adapter: metadata is not authenticated here, and production input masking and output secret screening remain separate requirements.

Run `uv run python -m unittest -v test_onboarding` for mocked-extraction policy/transport checks. These are not a live-model accuracy result. The optional sixth golden is unresolved and excluded from settled-case scoring.


### Step 8 verification — October 13, 2026

Twenty focused tests passed using mocked extraction, including business-unit mapping, unsupported-role ordering, transient retries, permanent provider rejection, malformed model output, rejected model-supplied role IDs, invalid Request handling, and multi-venue trainer assignments. The live local endpoint matched all five settled goldens on status, review reason, required fields, and applicable role/venue/login/date checks. After the business-unit fix, a live-model recheck passed the same five structured checks; an additional Sports ticket returned human_review / ambiguous_mapping with no recommendation. Free-text wording was not exact-scored. This small synthetic sample is not production accuracy evidence. The browser form also returned a standard-backed recommendation using the later human comment's start date.
