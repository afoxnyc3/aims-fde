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

Full table, per-question results and settings for the ten-question run below: [`retrieval_results.md` at the 14:51 run](https://github.com/afoxnyc3/aims-fde/blob/295b60d/use_case/evals/retrieval_results.md). The current [`evals/retrieval_results.md`](evals/retrieval_results.md) holds the later 15-question run (Step 6). Run on the real questions, 2026-10-27, one run per question per technique.

| Technique | Pass | Cited every gold | Avg calls | Avg evidence (chars) | Avg tokens | Median latency (s) |
| --- | --- | --- | --- | --- | --- | --- |
| Agentic RAG (BM25 `search_chunks`) | 9/10 | 7/8 | 2.2 | 16,252 | 10,516 | 5.5 |
| Direct corpus interaction (list / grep / read) | 10/10 | 8/8 | 4.5 | 13,922 | 17,665 | 5.8 |
| Agentic dense | 9/10 | 8/8 | 2.4 | 16,997 | 13,422 | 7.0 |
| **Agentic hybrid (BM25 + dense, RRF) — shipped** | 10/10 | 8/8 | 2.4 | 17,297 | 12,713 | 6.8 |
| Fixed pipeline (one hybrid retrieval, one answer) | 9/10 | 4/8 | 1 | 4,865 | 2,839 | 5.2 |

This is the 10-question run with the missing-fact answer rule (below), 2026-10-27 14:51. [`evals/retrieval_results.md`](evals/retrieval_results.md) now holds the later 15-question run, which adds the Step 6 associate's questions; see Step 6. Before that rule, the four agentic techniques tied at 8/10 pass and 8/8 cited, and every technique failed q01 and q05.

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

**What fixing the answer rule changed:** the prompt now checks, in order: a question about what is allowed that the standard doesn't address declines, even if it names a ticket; a fact the named ticket lacks is answered (what is missing, what the ticket shows, cited); a next step only if a record states it. q01 and q05 went from failing for every technique to passing. It took three wordings. The first made *any* missing fact an answer, and q03 (a promotion policy) stopped declining for every agentic technique. The second added "what to do next", and the model began advising who to ask for a missing email, which no record states. **Citation now separates the techniques.** q04 needs the role list and the status rule. Across all six runs on the real questions today, hybrid and direct corpus interaction cited both every time; dense cited the status rule in 4 of 6 runs and BM25 in 2 of 6. Substring scoring has false negatives (dense's q05: "recommendation", not "recommended") and false positives; both are kept for the Week 4 judge rather than fixed by loosening labels.

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

## Step 6: the demo

A live session on 2026-10-27 with the Technology Support Associate who works the onboarding queue. He typed five questions of his own. After each one he said whether he would act on the answer and whether the source convinced him, then what he wanted to ask but didn't. Follow-up questions clarified his answers. Recorded in three places:
- **The conversation:** a row in [`stakeholders.md`](stakeholders.md).
- **What it changed:** the line under "Week 3 — what the Step 6 demo changed" in [`decisions.md`](decisions.md), plus a new row on mirroring.
- **His questions:** q11–q15 in [`evals/retrieval.jsonl`](evals/retrieval.jsonl), in his words, with the system and club names made generic.

**What he said:** he would act on one answer of five, and only with a "but". No source convinced him, for one reason. The standard says *whether* a role gets a login, but his job is the **category** of access and its **scope** (venue or fitness-level), by job title. When the tool can't help, he mirrors a colleague who provides the same service, and he settles any discrepancy by asking the manager for a long-tenured person whose access is right.

**What the measurement says about his questions** (15-question run, [`evals/retrieval_results.md`](evals/retrieval_results.md)):
- **q11, q13, q14** (client access, Housekeeping Manager, a transfer) are labelled as routing answers, because the status rule routes them: human review, or for q11 read as a change to an existing employee, ignored as a permission change. **All 15 runs declined them** (three questions × five techniques), often after naming the reason ("the standard doesn't define a Housekeeping Manager role"). That is the next answer-rule change: "outside the standard, goes to human review" is an answer.
- **q12** (a trainer showing at another club's website) declines correctly everywhere. The corpus has no scope yet.
- **q15** (Level 3 trainer) passes for every agentic technique, and he still wouldn't act on it: the right answer from today's standard isn't the one his job needs.

| Technique | Pass (15) | Cited every gold (12) |
| --- | --- | --- |
| Agentic BM25 | 12/15 | 10/12 |
| Direct corpus interaction | 12/15 | 12/12 |
| Agentic dense | 12/15 | 10/12 |
| **Agentic hybrid — shipped** | 12/15 | 10/12 |
| Fixed pipeline | 10/15 | 4/12 |

Every agentic technique's three misses are the same three routing questions. A label review after this run tightened q11, q12, q14 and q15; re-scoring the saved answers against the new labels changed no result. Hybrid's two citation misses are q11 and q13, which it declined. The ten original questions all passed for hybrid again.

## Step 7: bring it to work

[`README.md`](README.md#tc3--retrieval), under "Bring it to work": the search it is for, and the data, model and approval swap lines, with the measured token count. **[YOU]** Confirm the lines marked there; they are claims about your company.

## Lessons learned

1. **Drafted questions measure nothing.** On the ten drafts, every agentic technique passed 10 of 10, so the comparison could not choose. The real questions from the ticket export separated them on the first run. *Recommendation:* label from tickets and people before building anything to compare, and treat a tie across techniques as a sign the questions are too easy.
2. **The scorer is part of the system, so review it like code.** Three labels scored the wrong thing. One gave direct corpus interaction a q05 "win" that disappeared when the label was fixed, and it had nearly become the decision's main argument. *Recommendation:* read the traces before trusting a pass rate, review labels with the same rigour as the endpoint, and move judgement calls to the Week 4 judge rather than loosening substrings.
3. **Most failures were answer behaviour, not retrieval.** q01 and q05 found and cited the right ticket in every technique, then declined. Fixing it took three prompt wordings: one broke q03's decline, and one invited advice no record supports. *Recommendation:* score "found the record" separately from "answered usefully", re-measure after every prompt change, and pin the measured rule order with a test.
4. **Citation separated the techniques; pass rate didn't.** Once answers were fixed, every agentic technique passed nearly everything. q04's second record told them apart: hybrid cited it in 6 of 6 runs, and BM25 in 2 of 6. *Recommendation:* score complete citations on multi-record questions, and repeat the run on the question that separates techniques before calling a one-question difference a finding.
5. **The bottleneck is the standard, and the queue already has an unwritten one.** The associate acted on one answer of five, and not because retrieval failed: the standard says whether a role gets a login, and his job runs on the category of access and its scope. What fills the gap today is mirroring a manager-confirmed, long-tenured colleague, which he reports works. *Recommendation:* demo to a real user before tuning retrieval further, and treat those reference accounts as the first draft of category and scope per role, instead of arguing against mirroring. On the app side, the next gain is "goes to human review" as an answer.

## Checklist

- [x] Ten labelled questions from the JSM export, two declines included
- [x] Schema: `solve()` unchanged; second contract recorded in the charter and decisions
- [x] Five techniques measured, table and settings in the repo, token count measured
- [x] `@app.api` endpoint over the TC2 data, sources on every answer
- [x] Retrieval decision row and four non-text answers
- [x] Runs in Docker, data mounted read-only
- [x] Real questions and re-run (2026-10-27)
- [x] Demo with the Technology Support Associate; five questions (q11–q15) labelled and scored; decisions line
- [x] Stakeholder row in my own words
- [x] Lessons learned reviewed and edited
- [ ] **[YOU]** Confirm the Bring-it-to-work lines
- [ ] **[YOU]** Loom, Maven post, two peer comments
