# TC3 submission

A question endpoint over the synthetic onboarding tickets and the draft access standard. It answers with the records it used, or declines. Five retrieval techniques were measured against labelled questions before one was picked. This page indexes each deliverable; the detail lives in the linked files.

**Loom:** **[YOU: link, ≤ 5 min — the endpoint answering two questions with sources, then the results table]**
**Pull requests (merged to `main`):** [#13](https://github.com/afoxnyc3/aims-fde/pull/13) corpus and labels → [#14](https://github.com/afoxnyc3/aims-fde/pull/14) measurement → [#15](https://github.com/afoxnyc3/aims-fde/pull/15) endpoint → [#16](https://github.com/afoxnyc3/aims-fde/pull/16) decision docs → [#17](https://github.com/afoxnyc3/aims-fde/pull/17) "Ask the records" panel

## Step 1: labelled questions

[`evals/retrieval.jsonl`](evals/retrieval.jsonl): ten questions, each with the page(s) that should answer it, its kind, the terms a passing answer must contain, and why. Format and page names: [`evals/README.md`](evals/README.md#retrievaljsonl).

- **Source:** a JSM ticket export of about 1,000 tickets (Oct 2025 to Sep 2026), read on a separate machine. The export never entered this repo. Only the question shape crossed over: real names became the synthetic names on the matching gold record, and each line's `origin` gives the kind of source and the month.
- **How real:** each line has a `strength`. Three are verbatim (q01, q03, q10), three are paraphrased clarifications (q05, q06, q07), and four are decision points (q02, q04, q08, q09). A decision point is a real situation that the ticket fields forced, but nobody wrote the question; the wording is ours. The Step 6 demo is the place to replace those four with a colleague's own words.
- **Top-k floor:** 3 of 10 need two records (q04, q08, q09), so top-1 is ruled out.
- **Declines:** q10 is a real request for a list of passwords; no record holds credentials, and none should. q03 asks to keep Level 1 booking access after a promotion. It came up on 14 real tickets, and the standard doesn't cover level-specific rights.
- **What replacing the drafts changed:** two drafts had no real counterpart (Lifeguard logins by club, an Aquatics Lead club change), so they were replaced. q08's "wrong channel" premise didn't hold up: in the export, 48 promotions arrive through the general request channel by design. The label now accepts any wording that says it isn't an onboarding request.

## Step 2: the schema

`solve()` was already implemented in TC1 and is unchanged. Questions get a **second contract**, `QuestionRequest` → `QuestionAnswer` ([`qa_schema.py`](../01_Product_Engineering/challenge/qa_schema.py)), with `sources`, `declined`, `decline_reason`, `dropped_citations` and the retrieval `trace`. Why a second contract rather than a `sources` field on `Response`: [`decisions.md`](decisions.md) (Week 3 / Step 2). The charter notes it.

## Step 3: the measurement

Full table, per-question results and settings: [`evals/retrieval_results.md`](evals/retrieval_results.md). Run on the real questions, 2026-10-27, one run per question per technique.

| Technique | Pass | Cited every gold | Avg calls | Avg evidence (chars) | Avg tokens | Median latency (s) |
| --- | --- | --- | --- | --- | --- | --- |
| Agentic RAG (BM25 `search_chunks`) | 9/10 | 7/8 | 2.2 | 16,252 | 10,516 | 5.5 |
| Direct corpus interaction (list / grep / read) | 10/10 | 8/8 | 4.5 | 13,922 | 17,665 | 5.8 |
| Agentic dense | 9/10 | 8/8 | 2.4 | 16,997 | 13,422 | 7.0 |
| **Agentic hybrid (BM25 + dense, RRF) — shipped** | 10/10 | 8/8 | 2.4 | 17,297 | 12,713 | 6.8 |
| Fixed pipeline (one hybrid retrieval, one answer) | 9/10 | 4/8 | 1 | 4,865 | 2,839 | 5.2 |

This is the run with the missing-fact answer rule (below). Before that rule, the four agentic techniques tied at 8/10 pass and 8/8 cited, and every technique failed q01 and q05.

The earlier draft-question runs (2026-10-24) are superseded. Every agentic technique passed 10 of 10 on the drafts, so the drafts didn't separate the techniques.

**Settings:**
- **Answer model:** `openrouter/anthropic/claude-sonnet-5.5`.
- **Turn budget:** 6.
- **Chunking:** none. One record per chunk, delivered whole.
- **Embeddings:** `openrouter/openai/text-embedding-3-small`.
- **Hybrid:** RRF with k = 60, over BM25 top 20 and dense top 20.
- **Pipeline:** reads the hybrid top 5.

**Embedding tokens: 30,353 to embed all 116 pages, measured** from the provider's `usage.total_tokens`.

**Variance:** one run per cell, so a one-question difference is noise until repeated.

**What the real questions found, before the answer-rule fix:** the four agentic techniques tied at 8/10, and they shared the same two failures. q01 and q05 ask about a fact the record doesn't hold. q01 asks for the new hire's email, which is blank. q05 asks whether the account was set up, but the ticket holds only a recommendation. Every technique found and cited the right ticket and said, correctly, that the fact was missing. But it put that behind `CANNOT ANSWER:`, and the endpoint turns that into a decline with no answer and no sources. The associate loses the useful part: "it isn't on the ticket, the ticket is needs_information, ask the requester." This is answer behaviour, not retrieval. The draft questions never asked about a missing fact, so they couldn't show it.

**What fixing the answer rule changed:** the prompt now checks, in order: a question about what is allowed that the standard doesn't address declines, even if it names a ticket; a fact the named ticket lacks is answered (what is missing, what the ticket shows, cited); a next step only if a record states it. q01 and q05 went from failing for every technique to passing. It took three wordings. The first made *any* missing fact an answer, and q03 (a promotion policy) stopped declining for every agentic technique. The second added "what to do next", and the model began advising who to ask for a missing email, which no record states. **Citation now separates the techniques.** q04 needs the role list and the status rule. Across four runs today, hybrid and direct corpus interaction cited both every time; BM25 cited the status rule in 1 of 4 runs and dense in 2 of 4. Substring scoring has false negatives (dense's q05: "recommendation", not "recommended") and false positives; both are kept for the Week 4 judge rather than fixed by loosening labels.

**What the label review found:** a code review of the labels caught three that scored the wrong thing. q03's forbidden phrases ("he keeps") could appear inside a correct refusal. q05 passed any answer containing "recommended", including "yes, it was set up". q08's reason term matched the ticket's own request-type field. After tightening them, direct corpus interaction's earlier q05 pass (3 of 3) disappeared. Its answers had named the recommendation without declining, and the loose label passed that. The real gap was never retrieval.

**What the pipeline's misses show:**
- **q04:** it never reached the standard: this run it declined ("the access standard page was not in the evidence"); earlier runs answered from precedent tickets.
- **q07, q08, q09:** passed on terms but cited only the precedent ticket, never the status rule that decides the routing.
- **Citations:** 4 of 8. With one retrieval it often names a precedent ticket in place of the standard page.

**What the first run found:** a 1,000-character hit cap cut the role list before the Cafe Associate row. Every search technique answered q04 from inference until hits carried whole records. The pass rate didn't show it; only reading the traces did.

## Step 4: the endpoint

`answer_onboarding_question` in [`app.py`](../01_Product_Engineering/challenge/app.py); retrieval in [`retrieval.py`](../01_Product_Engineering/challenge/retrieval.py), the decline rules in [`qa.py`](../01_Product_Engineering/challenge/qa.py). Its docstring, written for an agent reading it as the whole interface:

> Answer a question about onboarding tickets or the draft access standard, citing records. Send JSON {"question": "..."}: one plain-language question, up to 2000 characters. For example: which clubs give a Lifeguard a staff login; what standard role a ticket's job title maps to; what happened on a named new hire's ticket; how a kind of ticket is routed. Returns QuestionAnswer JSON. When answered, `answer` names its records in square brackets and `sources` lists them: SYN-* pages are synthetic onboarding tickets, STD-* pages are the draft v0.1 standard (unratified). If a named ticket lacks the fact asked for, the answer says so and cites the ticket; `declined` is false, so read the answer, not the flag, to learn whether the fact was found. When no record covers the question, including a policy the standard does not address, `declined` is true, `answer` is null and `decline_reason` says why; do not answer from elsewhere. `trace` lists every retrieval call. Read-only: no tickets or accounts are changed, and it never returns credentials. Invalid JSON is a validation error.

**On the decline question:** `declined: true`, no answer, empty `sources`, and the model's one-line reason; no password is produced. Re-verified in Docker on 2026-10-27 on the real questions: q10 and q03 decline with no sources, while q01 and q05 answer with the ticket cited. A policy question naming a ticket answers without granting or denying anything ([README](README.md#tc3--the-question-endpoint)).

## Step 5: the decision

[`decisions.md`](decisions.md), Week 3 rows:
- **Retrieval decision:** shipped, rejected, why, and what would change my mind.
- **The second contract.**
- **Explicit declines:** the similarity threshold was dropped because it can't separate the decline question on this corpus.
- **Whole-record chunks.**
- **Outcomes in the corpus.**

The four non-text answers are under "Week 3 — non-text content". **[YOU]** Check that the attachment types named there are the ones your queue actually sees.

## Step 6: the demo — **[YOU]**

Not done yet. It needs a real session with the Technology Support Associate:
1. Ask them to type five questions of their own.
2. After each answer, ask "Would you act on that answer?"
3. Then ask "Does the source it named convince you?"
4. Finally ask "What did you want to ask that you didn't?"

Then record it in three places:
- A row in [`stakeholders.md`](stakeholders.md), in your own words.
- The line under "Week 3 — what the Step 6 demo changed" in `decisions.md`.
- Their five questions, labelled, in `evals/retrieval.jsonl`.

## Step 7: bring it to work

[`README.md`](README.md#tc3--retrieval), under "Bring it to work": the search it is for, and the data, model and approval swap lines, with the measured token count. **[YOU]** Confirm the lines marked there; they are claims about your company.

## Checklist

- [x] Ten labelled questions from the JSM export, two declines included
- [x] Schema: `solve()` unchanged; second contract recorded in the charter and decisions
- [x] Five techniques measured, table and settings in the repo, token count measured
- [x] `@app.api` endpoint over the TC2 data, sources on every answer
- [x] Retrieval decision row and four non-text answers
- [x] Runs in Docker, data mounted read-only
- [x] Real questions and re-run (2026-10-27)
- [ ] **[YOU]** Demo, stakeholder row, five questions, decisions line
- [ ] **[YOU]** Confirm the Bring-it-to-work lines
- [ ] **[YOU]** Loom, Maven post, two peer comments
