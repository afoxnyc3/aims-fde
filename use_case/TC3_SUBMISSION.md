# TC3 submission

A question endpoint over the synthetic onboarding tickets and the draft access standard. It answers with the records it used, or declines. Five retrieval techniques were measured against labelled questions before one was picked. This page indexes each deliverable; the detail lives in the linked files.

**Loom:** **[YOU: link, ≤ 5 min — the endpoint answering two questions with sources, then the results table]**
**Branches:** `tc3/labels-and-corpus` → `tc3/retrieval-measurement` → `tc3/question-endpoint` → `tc3/decision-docs`

## Step 1: labelled questions

[`evals/retrieval.jsonl`](evals/retrieval.jsonl): ten questions, each with the page(s) that should answer it, its kind, the terms a passing answer must contain, and why. Format and page names: [`evals/README.md`](evals/README.md#retrievaljsonl).

- **Top-k floor:** 4 of 10 need two records (q03, q04, q08, q09), so top-1 is ruled out.
- **Decline:** q10 asks for a temporary password; no record holds one, and none should.
- **[YOU] Status: drafts.** The ten are shaped on the associate's job but were written for this run, not taken from a ticket or a colleague. Replace or confirm each one from a real source, fill its `origin` field, and re-run `measure_retrieval.py`.

## Step 2: the schema

`solve()` was already implemented in TC1 and is unchanged. Questions get a **second contract**, `QuestionRequest` → `QuestionAnswer` ([`qa_schema.py`](../01_Product_Engineering/challenge/qa_schema.py)), with `sources`, `declined`, `decline_reason`, `dropped_citations` and the retrieval `trace`. Why a second contract rather than a `sources` field on `Response`: [`decisions.md`](decisions.md) (Week 3 / Step 2). The charter notes it.

## Step 3: the measurement

Full table, per-question results and settings: [`evals/retrieval_results.md`](evals/retrieval_results.md). Third run, 2026-10-24, one run per question per technique.

| Technique | Pass | Cited every gold | Avg calls | Avg evidence (chars) | Avg tokens | Median latency (s) |
| --- | --- | --- | --- | --- | --- | --- |
| Agentic RAG (BM25 `search_chunks`) | 10/10 | 9/9 | 2.6 | 18,594 | 13,779 | 5.3 |
| Direct corpus interaction (list / grep / read) | 10/10 | 9/9 | 4.9 | 14,784 | 17,143 | 6.5 |
| Agentic dense | 10/10 | 9/9 | 2.1 | 15,384 | 9,841 | 5.3 |
| **Agentic hybrid (BM25 + dense, RRF) — shipped** | 10/10 | 9/9 | 2.0 | 14,551 | 8,638 | 5.2 |
| Fixed pipeline (one hybrid retrieval, one answer) | 8/10 | 7/9 | 1 | 4,813 | 2,729 | 5.3 |

**Settings:**
- **Answer model:** `openrouter/anthropic/claude-sonnet-5.5`.
- **Turn budget:** 6.
- **Chunking:** none. One record per chunk, delivered whole.
- **Embeddings:** `openrouter/openai/text-embedding-3-small`.
- **Hybrid:** RRF with k = 60, over BM25 top 20 and dense top 20.
- **Pipeline:** reads the hybrid top 5.

**Embedding tokens: 30,353 to embed all 116 pages, measured** from the provider's `usage.total_tokens`.

**Variance:** one run per cell, three runs in total. Agentic BM25 cited 8 of 9 in the second run and 9 of 9 in the third. Hybrid cited 9 of 9 in all three. A one-question difference is within noise.

**What the pipeline's misses show:**
- **q04:** it answered from precedent tickets, never reaching the standard.
- **q02:** it declined, because the role list gives only "Level 1" as an example level suffix. That ambiguity in the standard is worth raising with the Hospitality owner.

**What the first run found:** a 1,000-character hit cap cut the role list before the Cafe Associate row. Every search technique answered q04 from inference until hits carried whole records. The pass rate didn't show it; only reading the traces did.

## Step 4: the endpoint

`answer_onboarding_question` in [`app.py`](../01_Product_Engineering/challenge/app.py); retrieval in [`retrieval.py`](../01_Product_Engineering/challenge/retrieval.py), the decline rules in [`qa.py`](../01_Product_Engineering/challenge/qa.py). Its docstring, written for an agent reading it as the whole interface:

> Answer a question about onboarding tickets or the draft access standard, citing records. Send JSON {"question": "..."}: one plain-language question, up to 2000 characters. For example: which clubs give a Lifeguard a staff login; what standard role a ticket's job title maps to; what happened on a named new hire's ticket; how a kind of ticket is routed. Returns QuestionAnswer JSON. When answered, `answer` names its records in square brackets and `sources` lists them: SYN-* pages are synthetic onboarding tickets, STD-* pages are the draft v0.1 standard (unratified). When the records do not support an answer, `declined` is true, `answer` is null and `decline_reason` says why; do not answer from elsewhere. `trace` lists every retrieval call. Read-only: no tickets or accounts are changed, and it never returns credentials. Invalid JSON is a validation error.

**On the decline question:** `declined: true`, no answer, empty `sources`, and the model's one-line reason; no password is produced. Verified in Docker on 2026-10-24 ([README](README.md#tc3--the-question-endpoint)).

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

- [x] Ten labelled questions, decline included (**drafts**; replace from real sources)
- [x] Schema: `solve()` unchanged; second contract recorded in the charter and decisions
- [x] Five techniques measured, table and settings in the repo, token count measured
- [x] `@app.api` endpoint over the TC2 data, sources on every answer
- [x] Retrieval decision row and four non-text answers
- [x] Runs in Docker, data mounted read-only
- [ ] **[YOU]** Real questions and re-run
- [ ] **[YOU]** Demo, stakeholder row, five questions, decisions line
- [ ] **[YOU]** Confirm the Bring-it-to-work lines
- [ ] **[YOU]** Loom, Maven post, two peer comments
