# Your use case

**This directory is yours.** Everything else in this repository is teaching
material we wrote. This is the one place you work.

> **One use case, all ten weeks, no restarts.**

That rule is the whole design. The most common way this cohort goes wrong is a
student switching use cases halfway because the first one got hard — and then
arriving at fine-tuning with nothing to train against, and at the final report
with nobody to send it to. Choose something you actually own, at work, that
annoys you weekly.

---

## The files

### [`CHARTER.md`](./CHARTER.md) — the definition of what you are building

One page: the problem, whose problem it is, how you will know it worked, and the
input/output contract. It is the shortest file here and the only one everything
else depends on.

**Why it matters:** a vague charter does not produce a vague product, it produces
a product that cannot be evaluated. If you cannot say what a correct output looks
like, no amount of engineering downstream will tell you whether you built the
right thing — and you will find that out late.

### [`stakeholders.md`](./stakeholders.md) — the people, not the org chart

Everyone you spoke to: name, role, what you asked, what they said, what they
still owe you. It grows every week.

**Why it matters:** this is the difference between a project and an experiment.
Software that no named person is waiting for does not get adopted, and the people
who answer a question from a colleague they do not have to help are exactly the
people you will need again. Keeping the log costs a minute per conversation and
is unreconstructable afterwards.

### [`ecosystem.md`](./ecosystem.md) — what your firm will actually let you run

Where compute lives, what identity provider you are behind, how secrets arrive,
what egress is permitted, who signs off on a deployment. Answers from real
people, not assumptions.

**Why it matters:** most AI projects inside large firms do not fail on model
quality. They fail because nobody asked where the thing would run until it was
already built, and the answer turned out to be "not there." Every hour spent here
early is a week saved later, and the answers change how you build — not just
where you deploy.

### [`decisions.md`](./decisions.md) — what you chose, and what would change your mind

An architecture-decision log. For each real choice: what you picked, what you
rejected **after actually trying it**, the reasoning, and the condition under
which you would switch.

**Why it matters:** the last field is the one people skip and the one you get
asked about. *"We chose dense retrieval; we would move to hybrid if exact-match
queries went above about 20% of traffic"* is an engineering position. *"We chose
dense retrieval"* is a preference. You will have to defend these decisions out
loud, and reconstructing the reasoning six weeks later does not work.

### [`evals/golden.jsonl`](./evals/) — the examples you wrote by hand

A small set of inputs paired with the outputs you consider correct. You write the
first five yourself, deliberately, before any tooling exists.

**Why it matters:** these are the bar. Everything measurable about your project
is measured against them — whether synthetic data is realistic, whether a change
helped, whether a smaller self-hosted model is good enough to replace an API. Five
examples you thought hard about are worth more than five hundred generated ones,
because they encode a judgement no model has.

### [`evals/baseline.json`](./evals/) — the run itself, saved

The Week 4 harness run — your scorers over your cases against your endpoint —
saved as a file with a fingerprint of what was measured, alongside the
scorers, scenarios and generated failures that produced it. See
[`evals/README.md`](./evals/README.md) for the full list.

**Why it matters:** a number typed into a document cannot be compared by
anything and stops being true the moment you add a case. A saved run can be
re-run, compared and gated on — and `helpers.harness.compare()` refuses when
the case set changed, which is what stops a later "win" from being a change
of suite. Week 8's fine-tuned model has to beat this file.

### [`data/DATASHEET.md`](./data/DATASHEET.md) — what your data can and cannot prove

How the dataset was made, what it covers, what it does not, and what conclusions
it will not support.

**Why it matters:** synthetic data is generated from assumptions, and those
assumptions become invisible about a day after you make them. The datasheet is
what stops you reporting a number your data was never capable of supporting —
which is the failure that damages credibility rather than just the schedule.

### `app/` — the thing itself

Your application. It starts as a container that answers one endpoint and grows
each week.

**Why it matters:** it is the only artifact here that a non-engineer can be shown.

---

Nothing in this directory is busywork. Each file exists because something later
becomes impossible without it — and each one is far cheaper to write while the
work is fresh than to reconstruct from memory at the end.

---

## 🔒 Never commit real company data

`data/` is gitignored except its datasheet. That is deliberate and it is not
negotiable — this repository leaves your machine.

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


## Step 9 — container deployment

Built and ran with Docker Desktop on an arm64 Mac, targeting Azure's linux/amd64 architecture. From `01_Product_Engineering/challenge/`:

```sh
docker build --platform linux/amd64 -t tc1-onboarding:step9 .
docker run -d --name tc1-onboarding-step9 --platform linux/amd64 \
  -p 127.0.0.1:7860:7860 --env-file .env \
  -e GRADIO_SERVER_PORT=7860 -e GRADIO_ANALYTICS_ENABLED=False tc1-onboarding:step9
```

This checkout uses the challenge directory's `.env` for approved model configuration. It is supplied only at runtime; `.dockerignore` excludes `.env` files, the local virtual environment, and caches from the build context.

**Verified October 13, 2026:** the image is linux/amd64; the running process is Linux x86_64 with non-root UID 1000; `/health` returns status ok at `http://localhost:7860`. DEMO-001 submitted through the browser form returned recommended with the corrected October 16 start date, standard-backed assignment, and expected login and venue. A fresh container without an env file imported the contract and pipeline and contained no `.env` files or model API keys. This verifies a synthetic smoke test, not production accuracy.

| Dockerfile choice | Reason |
| --- | --- |
| Secrets arrive at runtime | Credentials stay out of image layers and can change without rebuilding. Production uses Key Vault rather than a laptop env file. |
| Run as appuser | Serving the application needs no root privileges; a non-root process limits its permissions. |
| Install dependencies before copying application code | Dependency layers remain cached when only code changes. |
| Install from uv.lock | The frozen export pins Python dependencies instead of resolving newer releases on each build. Base-image and uv tags remain separate versioning choices. |

**CDN dependency:** the browser loads `@gradio/client` from `https://cdn.jsdelivr.net/npm/@gradio/client/dist/index.min.js`. A browser on a network that blocks jsDelivr cannot connect the form, even when the container is healthy; this UI displays a connection error. The URL also omits a version, so a fresh fetch can load a newer client without an application rebuild, creating compatibility drift. For that environment, pin and bundle the client and its imports at build time, copy the bundle into the image, and serve it from this application. The current demo still uses the CDN; model API connectivity is a separate runtime dependency.

A container image captures the Linux userspace, Python runtime, system libraries, installed dependencies, application code, and startup command; a virtual environment mainly isolates Python packages and relies on its host runtime and OS. The image gives the platform team a packaged runtime to run on a compatible container host; secrets and deployment configuration remain external.

## TC3 — the question endpoint

`answer_onboarding_question(question_json: str) -> str` in [`app.py`](../01_Product_Engineering/challenge/app.py): send `{"question": "..."}`, get `QuestionAnswer` JSON with the answer, the records it cites in `sources`, and the trace of every retrieval call. Retrieval is agentic hybrid (BM25 + embeddings, RRF) over 116 pages: 113 synthetic tickets and 3 draft-standard pages. Why that technique: [`decisions.md`](decisions.md) (Week 3); the measurement: [`evals/retrieval_results.md`](evals/retrieval_results.md).

**On the decline question** ("What temporary password should I give a new Lifeguard?") it returns `declined: true`, no answer, empty `sources`, and the model's one-line reason; no password is ever produced. Any answer that cites no real record is declined the same way.

Run it locally from `01_Product_Engineering/challenge/` with the data file in `use_case/data/` (gitignored):

```sh
export RETRIEVAL_MODEL=openrouter/anthropic/claude-sonnet-5.5   # the model the table was measured on
uv run --env-file .env python app.py
uv run --env-file .env python measure_retrieval.py   # re-scores every technique; about $1-2
uv run python -m unittest test_onboarding test_corpus test_retrieval test_qa   # no keys needed
```

`.env` holds `OPENROUTER_API_KEY`. Set `EMBED_API_BASE` / `EMBED_API_KEY` to send embeddings through a gateway instead.

In Docker the corpus is mounted read-only, never copied into the image:

```sh
docker run -p 127.0.0.1:7860:7860 --env-file .env \
  -v "$PWD/../../use_case/data:/data:ro" -e CORPUS_PATH=/data/synthetic_v1.jsonl \
  -e RETRIEVAL_MODEL=openrouter/anthropic/claude-sonnet-5.5 tc3-retrieval
```

**Verified 2026-10-24 in Docker:** non-root (UID 1000), `/data` read-only, no data in the image. The endpoint answered q03 citing both gold records, answered q04 from the standard pages, declined the password question with no sources, and rejected an empty question as invalid input.

## Bring it to work

**Project:** We can't decide which roles keep seats under a fixed AI-tool
seat budget until someone clears analysis of the tool's chat export, which
may contain personal and confidential data. The classifier labels the kind
of work each conversation was for, so we can see which roles get value
from a seat.

- **Data:** Generate from a written description of the role mix (functions
  and approximate headcounts), not from the export. The synthetic
  conversations test the classifier's labels before any real record is
  touched. Joining the real export to roles happens only after approval,
  under the controls below. Owner of the real export: IT, as admin of the tool.
- **Model or endpoint:** qwen3:8b via Ollama on a managed, encrypted laptop;
  real export content does not leave the device. Latency was measured on
  ticket generation (~300-token outputs); classification (long input, short
  output) is not yet measured. Expected volume: a few thousand conversations
  per export, so batch time depends on that measurement.
- **Access or approval:** Naming a privacy reviewer for employee-conversation
  analysis is the first step. That reviewer and the CTO (system owner) then
  sign off on: employee notice under the acceptable-use policy; retention and
  deletion covering every copy of the export; scope limited to conversation
  records and usage metadata; and results reported by role, never by person.

### TC3 — retrieval

**[YOU: confirm or rewrite.]** Technology Support Associates decide new-hire access by searching Confluence and comparing peer accounts in the club-management system, then answer from memory; nobody has measured whether that search finds the right page, and the answer never cites one.

- **Data:** **[YOU]** resolved onboarding tickets from JSM plus the versioned role standard once ratified. Text only today; screenshots and scanned forms attached to tickets would be next (see decisions.md, non-text). Real tickets are masked before indexing.
- **Model or endpoint:** **[YOU: confirm the route is approved for real ticket text.]** Answer model `claude-sonnet-5.5` through OpenRouter (approved); embeddings `text-embedding-3-small` through OpenRouter, or `nomic-embed-text` on Ollama inside the network if ticket text may not leave it (both were tested on 2026-10-24). Re-indexing cost: **30,353 embedding tokens for 116 pages, measured**; about 260 tokens per page.
- **Access or approval:** **[YOU]** read access to the JSM onboarding project for the indexer, approval for an embedding route for masked ticket text (or the local model), and the role-standard owners' sign-off before standard pages are indexed as authoritative.

