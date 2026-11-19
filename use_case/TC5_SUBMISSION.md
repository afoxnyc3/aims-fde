# TC5: The Question Endpoint, Built a Second Way and Measured

> Submitted 2026-11-10 (Known Issues updated 2026-11-12 with a re-measurement; headline and unnecessary-asks count corrected 2026-11-18, and the several-lookups answers graded in a re-run the same day, see [Corrections after review](#corrections-after-review-2026-11-18); the Loom shows the 2026-11-10 state and still says the original headline). **Loom:** https://www.loom.com/share/1a3b85c2674d4b27aeb5fd5ce7c89e14 (4 min). **Deck:** [`demo/tc5_demo.html`](demo/tc5_demo.html).
> Architecture row decided 2026-11-07. Step 1 marks confirmed, Service Desk session held and Step 7.2 line recorded on 2026-11-09. Role rulings and the v0.5 re-run on 2026-11-10.

## TL;DR

I exposed the onboarding question endpoint as an MCP server and measured it against the in-app tool. **Transport is not the cost:** raw search over MCP costs what the in-app tool costs. **The guarded tool is what ships.** The caller's model reads 4–6x fewer tokens, and every guard runs inside the server. The price is 1.2–2.8x the total tokens and 2.5–4.5x the time.

**Decision:** a private, gated, read-only tools service. The onboarding app calls it as an internal API. Staff using Claude reach it over MCP.

**And the agent got better, by less than the first headline said.** **On current labels, the same 29 real test tickets went from 22 right to 27 right, with 0 over-grants in 3 recommendations.** The TC4 baseline stays 14 of 29 as scored on 2026-11-03, but the move from 14 to 22 is the owner's surname ruling relabelling 8 tickets, not the agent: the same saved TC4 outputs score 22 on today's labels. The agent and standard v0.5 account for the 5 tickets from 22 to 27. Not held out; sources and commands are in [Results after the 2026-11-10 rulings](#results-after-the-2026-11-10-rulings). The model barely changed. The standard did.

---

## Results after the 2026-11-10 rulings

Same 29 real test tickets as TC4, current agent, standard v0.5. **Not held out:** this split has been read closely, and one check below was added after a test run.

**Headline: on current labels, 22 to 27 of 29 test tickets right, and 0 over-grants in 3 recommendations.**

| | TC4 run, labels at run time (2026-11-03, v0.3) | Same TC4 outputs, current labels | TC5 run, current labels (2026-11-10, v0.5) |
| --- | --- | --- | --- |
| Test, right outcome | 14 of 29 (0.48) | 22 of 29 (0.76) | **27 of 29 (0.93)** |
| Test, over-access | 2 of 5 recommendations | 2 of 5 recommendations | **0 of 3 recommendations** |
| Unnecessary asks (test) | 8 | 0 | **0** |
| Dev, right outcome | 25 of 29, 0 over-access | 26 of 29 | **28 of 29**, 0 over-access in 11 recommendations |
| Synthetic grid | 168 of 180, 11 over-access | labels unchanged | **174 of 180, 2 over-access** |

**How to read the test rows.**
- **The like-for-like gain is 22 to 27, five tickets.** The first column is the TC4 baseline as it was scored. The middle column is the same saved outputs against today's labels, with no re-run. The step from 14 to 22 is the owner's surname ruling (2026-11-07): 8 test tickets moved from `recommended` to `needs_information`, which is what the TC4 agent already answered ([TC4, name policy](TC4_SUBMISSION.md#name-policy-2026-11-07)). The five tickets the TC5 run gained are the two TC4 over-grants (TKT-63, TKT-408) and three asks on exception tickets (TKT-155, TKT-414, TKT-421), all now sent to a person.
- **"Zero over-access" rests on 3 recommendations.** The TC5 run recommended 3 of the 29 test tickets (TKT-119, TKT-478, TKT-485) and all 3 carry a `recommended` label. The labels say recommend on 5; the other 2 (TKT-334, TKT-390) went to a person, which are the two misses. The TC4 run recommended 5, and 2 of those were over-grants. Three is too few to claim a rate. Dev adds 11 recommendations with 0 over-grants, and the grid has 2 over-grants in 180 scenarios.
- **Unnecessary asks are 0 in the TC5 test run.** An unnecessary ask is a `needs_information` answer on a ticket labelled `recommended` (`unnecessary_ask` in [`evals/harness.py`](evals/harness.py)). The run file records a count of 0 and its rows recompute to 0. This table said 1 before 2026-11-18; no saved file supports a 1.

**Where each number comes from.** No model calls; both commands read saved files only.
- 14, 22, the TC4 over-access of 2 and the TC4 unnecessary asks of 8 and 0: `python3 use_case/evals/run.py --committed`, which reads [`evals/real_v03/results/endpoint_test.json`](evals/real_v03/results/endpoint_test.json) and rescores it against [`evals/real_v03/golden.jsonl`](evals/real_v03/golden.jsonl). The test split has the same status labels in [`evals/real_v05/golden.jsonl`](evals/real_v05/golden.jsonl), so 22 holds on either label file.
- 27, the 3 recommendations, the 0 over-grants and the 0 unnecessary asks: [`evals/real_v05/results/endpoint_test.json`](evals/real_v05/results/endpoint_test.json), by counting its rows (`actual` against `expected`, and the `no_over_privilege` score). Its `meta.metrics` block records `unnecessary_asks` count 0 and `over_privilege` count 0. The recommendation counts of 5 and 3 are rows whose `actual` status is `recommended` in the two run files.
- Dev: 25, 28 and the 11 recommendations from `evals/real_v03/results/endpoint_dev.json` and `evals/real_v05/results/endpoint_dev.json`. The 26 is the saved TC4 dev outputs matched by status against `evals/real_v05/golden.jsonl`; it is 27 against `real_v03` labels, and the difference is TKT-293, relabelled in `real_v05` to `needs_information`. The TC4 run recommended that ticket, so on current labels it is a missed ask in the TC4 dev run.
- Grid: `endpoint_grid.json` in the same two results folders.

**What moved it:** six owner and Service Desk rulings that closed role mappings and the exception order, a business-unit scope and a per-title staff group in the decision code, and a deterministic check for systems outside the role bundle. Rulings in [`decisions.md`](decisions.md#owner-decisions-2026-11-10); labels and runs in [`evals/real_v05`](evals/real_v05/README.md). `real_v03` stays the frozen TC4 record.

**Failure analysis: our first zero was luck.** A morning run showed over-access 2 → 0. The two TC4 over-access tickets went to a person only because their roles were still unmapped. Once mapped, the agent recommended both, and both ask for systems outside the bundle (one for a scheduling app, one for several business systems). Extraction didn't flag either. The fix is in code, not the prompt: the standard names those systems, and an intake that names one becomes an exception. Validated on dev and on the synthetic grid, which it was not tuned on.

**Known risk, accepted by the owner.** NY Group Fitness Instructors are recommended Senior Group Fitness Instructor, the current SOP, which carries staff admin. "0 over-access" is measured against labels that accept that SOP. Every such recommendation carries a warning, and the exception ends when the role is cleaned up with stakeholders.

---

## Step 2: Why a Second Way

I walked Session 10's ordering for the question endpoint (`search_hybrid` in a tool loop):

1. **Is it already an HTTP API at work?** No. Retrieval over the standard and the past tickets exists only in this codebase.
2. **Does anything outside the codebase need to find it?** Yes. Every stakeholder role in `stakeholders.md` has a seat in our Claude workspace (`ecosystem.md`, Week 5, from the project owner). The Service Desk confirmed it on 2026-11-09: the Technology Support Associate uses Claude Desktop every day. Staff should reach the capability from Claude without importing our code. **Second way: an MCP server.**
3. **Many calls, or large responses?** Also yes: whole records and several searches per question. That makes **Code Mode the closest alternative I didn't build.** It would keep the 4–8 KB of records each search returns out of every model's context. The guarded tool already keeps them out of the caller's context. Code Mode also means running model-written code, which needs a sandbox and a security review. The owner states a sandbox is already approved (owner, 2026-11-19). A security review is not recorded as done. It becomes the pick when the Step 6 switch condition fires.

---

## Step 3: What I Built

`01_Product_Engineering/challenge/mcp_server.py`: FastMCP 4.1.6 over stdio. Two tools, one switch (`MCP_TOOLSET`).

| Tool | Role |
| --- | --- |
| `answer_onboarding_question` | **Shipped default.** Wraps `qa.answer_question`. Declines, citation checks and the no-credentials rule all run inside the server. The caller gets the answer, its sources and any decline reason. Never raw records. |
| `search_hybrid` (`MCP_TOOLSET=search`) | The same raw search Way 1 gives its model. Used only for the like-for-like measurement. |

**Middleware**
- **`AuditCounter`** logs the shape of every call: tool, argument keys, response bytes, ms, error class, whether it reached the capability, and the model tokens the server spent on it. It never logs values or results. Like Way 1's counter, it counts only calls that reached the capability.
- **`ToolErrorMessages`** turns unknown tools and bad arguments into short messages that never echo the input. An upstream outage becomes a fixed `UPSTREAM_UNAVAILABLE` marker. Our measurement client aborts the run when it sees that marker, which is the same contract Way 1 has. An outside client like Claude Desktop doesn't abort. Its model reads the marker.

**Input guard:** the guarded tool rejects an empty, blank or over-2,000-character question with a clear "Bad arguments" message before the capability runs. These calls are logged but not counted.

**Why custom error text:** FastMCP's default validation message echoes the arguments back, and arguments can carry ticket text. Ours never echo them.

| Toolset | Request | Message to the model |
| --- | --- | --- |
| search | unknown tool `lookup_team` | `Unknown tool 'lookup_team'. Available tools: search_hybrid.` |
| search | `{"query": "...", "k": "lots"}` | `Bad arguments for 'search_hybrid': k: Input should be a valid integer, unable to parse string as an integer.` |
| search | `{"k": "lots"}` | `Bad arguments for 'search_hybrid': query: Missing required argument; k: Input should be a valid integer, ...` |
| shipped | `{"question": ""}` (or blank, or over 2,000 chars) | `Bad arguments for 'answer_onboarding_question': question: ...` (rejected before the capability runs; logged, not counted) |
| shipped | unknown tool `search_hybrid` | `Unknown tool 'search_hybrid'. Available tools: answer_onboarding_question.` |

**Tests:** `python -m unittest test_mcp_server test_measure_tc5` runs 18 + 4 tests offline. They include two overlapping guarded calls, each of which counts only its own model tokens.

**Docker (2026-11-07):** the image builds. `docker run -i ... python mcp_server.py` lists only `answer_onboarding_question`, and it answered the one-lookup question (Front Desk Associate) through that tool.

### Connect Claude Code or Claude Desktop (`.mcp.json`)

```json
{"mcpServers": {"onboarding-qa": {"command": "uv",
  "args": ["run", "--directory", "<absolute path>/01_Product_Engineering/challenge",
           "--env-file", "<absolute path to .env>", "python", "mcp_server.py"],
  "env": {"CORPUS_PATH": "<absolute path to synthetic_v1.jsonl>",
          "MCP_AUDIT_LOG": "<absolute path>/mcp_audit.jsonl", "MCP_PRELOAD": "1"}}}}
```

Two settings are required:
- **`--env-file`** gives the server its model and key. The app doesn't load `.env` itself. Without this flag, every guarded call returns `UPSTREAM_UNAVAILABLE`.
- **`MCP_AUDIT_LOG`** must be set in any deployment that relies on the counts or the switch conditions. If it's unset, no log is written.

---

## Steps 4 and 5: Both Ways, Measured

**Setup**
- `measure_tc5.py` with `anthropic/claude-sonnet-5-5`, called **directly on Anthropic's API** through LiteLLM (no API base set). TC3 and TC4 went through OpenRouter, so compare these numbers with earlier weeks' carefully.
- Same system prompt, 6-turn loop limit, 3 runs per cell, **medians**. Measured 2026-11-07.
- The MCP tool has **the same description and parameter wording as Way 1's schema**, but the two aren't byte-identical. FastMCP adds `"default": 4` on `k` and `"additionalProperties": false`. `test_mcp_server` pins that difference.
- Way 2 runs against **one warm server session per size**, because Claude Desktop keeps a stdio server alive for the whole session.
- Real-size rows are in `use_case/evals/tc5_measure_run{1,2,3}.jsonl`, written with `--out` (the script's default file name is `tc5_measure.jsonl`). The demo-size rows and an earlier real-size round, both taken before the schemas were matched, are in `tc5_measure_schema_unmatched_run{1,2,3}.jsonl`.
- The several-lookups request was run again on 2026-11-18 to grade its answers, 3 runs per way, same model and settings. Those rows, with the answer text, are in `use_case/evals/tc5_measure_graded_2026-11-18_run{1,2,3}.jsonl`.

**Startup cost: about 2 s, once per session.** With `MCP_PRELOAD`, the server loads and embeds the corpus before it answers the handshake. The handshake takes 1.82–1.92 s and the first `list_tools` call takes 0.07–0.10 s. That holds for both the raw-search and the guarded session, each timed on its own. Earlier rounds warmed on the first call instead, at 1.8–3.0 s total. Those rounds aren't on disk: only this round and the unmatched round are. An earlier version of the harness started a new server for every request and put that cost into every row. Those numbers are superseded.

### Real size

Whole records, 4 by default. The model sets `k` up to 8, so a raw-search response is **4.1–8.4 KB** (run averages). Way 2b is the guarded tool used the way an outside client would use it. *Client* tokens are what the caller's model reads. *Total* tokens add what the server spends on its internal retrieval loop.

| Request | Way | Model calls (client) | Capability calls | Seconds | Tokens (client) | Tokens (total) | Facts right of 6, per run (median)† |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| one lookup | 1 tool | 2 | 2 | 4.9 | 9,136 | 9,136 | not scored |
| one lookup | 2 MCP raw search (warm) | 2 | 2 | 5.6 | 8,991 | 8,991 | not scored |
| one lookup | 2b MCP guarded (warm) | 2 | 1 guarded call* | 12.0 | 2,346 | 11,271 | not scored |
| several lookups | 1 tool | 3 | 5 | 10.4 | 25,668 | 25,668 | 6, 6, 6 (6) |
| several lookups | 2 MCP raw search (warm) | 3 | 5 | 12.1 | 19,498 | 19,498 | 6, 6, 6 (6) |
| several lookups | 2b MCP guarded (warm) | 2 | 3 guarded calls* | 46.7 | 4,491 | 71,299 | 6, 6, 6 (6) |

\* For 2b, capability calls count calls to the guarded tool. Each call runs its own retrieval loop with several searches the client never sees (`server_model_turns` in the audit log). These cells don't compare with the search counts above them.

† The facts column comes from a separate re-run on 2026-11-18 (`use_case/evals/tc5_measure_graded_2026-11-18_run{1,2,3}.jsonl`), not from the 2026-11-07 runs that give the other columns. The old run files kept no answer text, so they cannot be graded. n=3 per way. This is not a significance test. The re-run's own cost, from the same files, is in the next table.

**The graded re-run, several lookups, 2026-11-18** (medians of 3; per-run values in brackets; all from `use_case/evals/tc5_measure_graded_2026-11-18_run{1,2,3}.jsonl`)

| Way | Facts right of 6 | Seconds | Tokens (client) | Tokens (total) |
| --- | ---: | ---: | ---: | ---: |
| 1 tool | 6 (6, 6, 6) | 17.0 (14.0, 17.0, 18.1) | 41,423 | 41,423 (41,423, 24,617, 43,663) |
| 2 MCP raw search (warm) | 6 (6, 6, 6) | 10.5 (11.7, 10.3, 10.5) | 32,084 | 32,084 (32,222, 32,084, 24,592) |
| 2b MCP guarded (warm) | 6 (6, 6, 6) | 41.1 (30.2, 46.0, 41.1) | 4,050 | 88,120 (88,120, 90,801, 85,774) |

In this re-run the tool and raw search each took a 4th model turn in 2 of 3 runs (`model_calls` 4, 3, 4 and 4, 4, 3), which is why their tokens are higher than on 2026-11-07. The guarded tool cost about 2.1x the tool's total tokens and about 2.4x its time here, against about 2.8x and 4.5x on 2026-11-07 (`use_case/evals/tc5_measure_run{1,2,3}.jsonl`). Session start-up in the re-run was slower than the "about 2 s" above: the handshake took 3.5 to 4.7 s (`mcp_session_start` in `use_case/evals/tc5_measure_graded_2026-11-18_run{1,2,3}.jsonl`).

**Per run, several lookups:** the tool made 5, 5 and 5 searches, in 3 turns each. Raw-search MCP made 5, 7 and 5. The 7-search run took a 4th turn and cost 42,340 tokens. The guarded server ran 9, 9 and 10 model turns of its own across 3–4 sub-questions (`server_model_turns`, from its audit log).

**Answer checks**
- **All 18 real-size runs answered**, meaning none declined according to `retrieval.decline_reason` on the final text. For 2b this check reads the client's wording, so a paraphrased decline from the server would still pass. The harness now also counts the server's own `declined` field (`server_declined`), but these runs predate it. Treat 2b's "answered" as the weaker text check.
- **All 9 one-lookup runs named the expected role.** `role_named` is a substring check for "front desk associate", so an answer that names the role in order to reject it would also pass. Read this at n=9, not as grading.
- **The several-lookups answers are now graded, in a re-run on 2026-11-18: every way got 6 of 6 facts right in all 3 runs.** n=3 per way, 9 answers. This is not a significance test, and 9 perfect answers cannot show that the three ways are equally accurate, only that none of them got a fact wrong here.
  - **The six facts:** a role and a mailbox answer for each of the three hires. The expected values come from the synthetic standard in `01_Product_Engineering/challenge/standard_v0_1.md`. The roles are Front Desk Associate, Lifeguard and Personal Trainer. That file has no mailbox column and never uses the word, so the right mailbox answer for each hire is "the standard does not say". A yes is wrong and a flat no is wrong. So three of the six facts test whether the answer avoids making up a rule, not whether it finds one.
  - **The scorer** is `score_several_lookups` in `01_Product_Engineering/challenge/tc5_facts.py`, a fixed-pattern text check with no model. A fact is right only if the answer states the correct value for the correct hire. Naming a value in order to reject it is wrong. A role counts only in that hire's own line, clause, table row or the bullets under its heading, and only right after a cue such as "use" or "Role:", so swapped roles score wrong in the layouts tested. A yes next to a hedge ("the standard does not say, but yes") scores wrong. `test_tc5_facts.py` covers right, wrong, partial, swapped, rejected-value, prohibited-role and hedge-then-grant answers.
  - **The scorer was corrected after reading the answers.** Earlier versions, written before the first commit, marked some of the 9 answers down. Those versions and their scores were not committed, so how many answers and by how much cannot be reproduced from this repo and is not given here. Read by hand, all 9 answers are 6 of 6. The misreads were remarks such as "that ticket field is not a mailbox entitlement" taken as a no, and "I can't give the Lifeguard answer for your club" taken as rejecting the role. Each misread phrasing is now a test case. The scores in the run files are the final scorer's, written back with `python tc5_facts.py --write`, and they match the hand reading on all 9.
  - **The scorer was then found too generous, and fixed.** A second reader ran hand-written answers through the first committed scorer and some scored too high: fully swapped roles scored 6 of 6, some rejections ("would be the wrong choice", "does not apply") counted as stating the role, and a yes next to a hedge counted as "not stated". Those cases are now tests and score wrong. A second round of hand-written answers found a further hole, roles swapped under headings scoring 6 of 6, and a third round found that "Lifeguard: no exact match in the standard" was credited as the Lifeguard role. A fourth round found that a role named and then said to be missing ("Lifeguard: Lifeguard is not in the standard") was still credited. A fifth round (2026-11-19) found two more answers that scored 6 of 6: a prohibition around the right role ("It is forbidden to use Front Desk Associate") was still credited, and a hedge followed by a grant ("The standard does not say, but all three are issued a company mailbox") still counted as "not stated". They now score 5 and 3 of 6, and the tests were written first and failed first. All of these are fixed and tested. The reader's batches of hand-written answers were not committed, so their sizes and how many scored too high in each round cannot be reproduced from this repo and are not given here. What is committed is each case that was found, as a test in `test_tc5_facts.py`, and the scorer from its first committed version on. The scorer catches the swaps and rejection wordings in its tests, not every possible one: for example a longer made-up role name such as the role followed by "Instructor" still scores as the role. "Lifeguard is missing from the standard" is also still credited. It errs the other way too: "use Front Desk Associate, since Hospitality Associate is not a role in the standard" is right and scores wrong. The 9 saved answers still score 6 of 6, and the same reader agreed by hand that each is 6 of 6. The result rests on the two hand readings first and the scorer second. The scorer is a pattern check fitted to these answers and to the wrong answers we thought of, so do not trust it on new answers without reading them.
  - **One guarded sub-call declined.** In run 3 the guarded server declined the Lifeguard sub-question (`server_declined` 1, `answered` false in `tc5_measure_graded_2026-11-18_run3.jsonl`). The client's answer still named the Lifeguard role and said the standard does not cover mailboxes for all three, so the text scores 6 of 6, but it had no sources for that hire. The tool and raw search had no declines.

**What this means for the decision.** On this request the guarded tool's extra cost bought no extra right answers: all three ways scored 6 of 6, and the guarded tool cost 88,120 total tokens and 41.1 s against 41,423 and 17.0 s for the in-app tool (`use_case/evals/tc5_measure_graded_2026-11-18_run{1,2,3}.jsonl`). So the decision to ship the guarded tool cannot rest on accuracy: it rests on the guards running inside the server and on the caller reading about 10x fewer tokens (4,050 against 41,423). The price is about twice the tokens, more than twice the wait, and in this sample one declined sub-question the cheaper ways answered, and whether that wait is acceptable is still open (see [Open](#open)).

### Demo size

Each hit is cut to 300 characters, and only raw search was run. **This is not like for like.** These rows come from the round before the MCP tool's description was matched to Way 1's, and demo size wasn't re-run afterward. Read them for the size effect, not to compare the two ways.

| Request | Way | Model calls | Capability calls | Seconds | Tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| one lookup | 1 tool | 5 | 7 | 14.0 | 24,310 |
| one lookup | 2 MCP (warm) | 6 | 6 | 14.0 | 23,414 |
| several lookups | 1 tool | 5 | 10 | 15.3 | 30,476 |
| several lookups | 2 MCP (warm) | 6 | 10 | 15.7 | 35,406 |

### Parallel tool calls: yes

The first turn asked for 1–4 tool calls at once (`len(msg.tool_calls)`). Capability calls usually exceed model calls, so the round-trip argument doesn't apply to this model.

---

## Findings

**1. Transport isn't the cost.** With matched schemas and a warm server, raw search over MCP matches the in-app tool's medians on searches (2 and 5) and on turns.
- Tokens: 8,991 vs 9,136 on one lookup, and 19,498 vs 25,668 on several. On several lookups, MCP's searches happened to return smaller records (4.1 vs 5.5 KB). That gap comes from the queries the model chose, not from the transport.
- Counts don't match run for run. On several lookups, the tool made 5, 5, 5 searches and MCP made 5, 7, 5. In the unmatched round on disk, the tool made 6, 5, 7 and MCP made 7, 5, 5. So 7-search, 4-turn runs happen on both paths. At this n, there's no proof that matching the description made them rarer for MCP.
- MCP's real cost is about 2 s once per session, plus a process to own and secure.

**2. The guarded tool is subagent-shaped.** The records stay inside the server, so the caller's model reads 4–6x fewer tokens (2,346 vs 9,136; 4,491 vs 25,668).
- **Total tokens go up:** about 1.2x on one lookup and about 2.8x on several. On several lookups, the client split the question into 3–4 calls, and each call ran its own retrieval loop.
- **It's slower:** 12.0 s and 46.7 s. The extra time isn't startup. With the corpus preloaded, the one-lookup median is 12.0 s. In the unmatched round, where the first question paid for loading, it was 10.7 s. The time goes to the server's own 2-turn model loop, which runs behind the client's 2 turns.
- **Part of the several-lookups time comes from our harness.** The client asked for all three calls in one turn, and our measurement loop sends them one at a time. A client that sends them together could finish closer to one loop's time if the server runs them concurrently. That's untested, and the server's per-call token counter assumes calls don't overlap.
- **The trade:** a clean caller context and the guards, paid for in total tokens and time.

**3. Demo size doesn't flatter this endpoint. It breaks it.** At 300 characters the role row gets cut off, and the model searches until it hits the turn limit. Only 1 of the 12 demo-size runs answered at all, and none named the role.

**4. The client can't see the server's work.** Capability calls are counted twice: by the client loop and by the server's `AuditCounter`. The two counts agreed on all 18 MCP rows. No call failed or was rejected in these runs (`server_failed` = 0), so the unit tests cover the failure path, not this data. The guarded tool's model tokens show up only in the server's log. The caller's own meter misses about 80–95% of the cost.

**5. Small n. Read the medians.** Across rounds, raw-search several-lookups runs ranged from about 19K to 44K tokens, more than 2x. Whether the model took a 4th turn drove that range.

### At 10x Volume

These figures are derived from the measured rows, not measured at 10x.

- **Cost per question tracks model turns, not searches.** Each turn re-reads everything gathered so far. In the tool rows, 5 searches in 3 turns cost about 23–26K tokens (raw-search MCP cost 19.4K, with smaller records). The 7-search runs that needed a 4th turn cost 42–44K.
- **Shipped guarded path:** about 11K tokens per question for one lookup and 71K for several, counting all chat-model tokens. Embedding the question adds a few tokens that aren't counted.
- **Service Desk volume:** about 5 onboarding or access requests a day (Technology Support Associate, 2026-11-09). At 10x that's 50 a day, or **about 0.55M–3.6M tokens a day**, measured against the tokens-per-question budget reviewed monthly (Step 6).
- **What changes the slope is per-question cost.** Doubling record size would roughly double the accumulated context, and so the per-turn cost, for the tool and for raw-search MCP. The guarded tool keeps records out of the caller's context. Code Mode would keep them out of every model's context.

### Harness Fixes After These Runs

From a code review on 2026-11-08. These fixes have not been re-measured.
- The server's per-call token counter is now kept per call instead of in a shared global. The measured calls ran one at a time, so the committed numbers aren't affected.
- Way 2 now answers non-object tool arguments with a message, the same way Way 1 does. No such arguments occurred in these runs.
- `HIT_CHARS` is now applied only when the server runs, not on import.
- The audit log now records only known argument names.

---

## Step 6: The Architecture Row

Decided by the owner on 2026-11-07 and copied into [`decisions.md`](decisions.md#week-5--architecture-row-tc5). The row names roles only, with no product or vendor names for the identity provider, vault or host.

### Decision

Expose the capability as tools on a **separate, gated tools service, hosted privately**. The service has two kinds of client:
- **The onboarding app**, which calls it as a direct internal API with no model in the path.
- **Staff using Claude**, who reach it over MCP.

The guarded `answer_onboarding_question` tool (built and measured above) is its first tool.

- **Identity:** the organization's SSO only. No user credentials are stored. SSO groups map to roles. A versioned policy table decides which tools, and which business-unit rows, each role can reach. Default deny. Read-only in v1.
- **System of record:** each consumer (the tools service and the onboarding app) gets its own least-privilege, read-only service account. Secrets live in a vault, reached through managed identity.
- **Rollout:** Service Desk pilot first. Widen once the sign-in, per-unit filtering and deny tests pass.

### Rejected

- **Raw search over MCP** (built and measured). With matched descriptions, its median searches and turns equal the in-app tool's (8,991 vs 9,136 tokens on one lookup; 19,498 vs 25,668 on several, where the gap is smaller returned records, not the transport). It buys reach, but it hands outside models whole records and skips the guards.
- **Code Mode, until the trigger below fires.** It would keep intermediate records out of every model's context. The guarded tool already keeps them out of the caller's, and Code Mode needs a sandbox and a security review. The owner states a sandbox is already approved (owner, 2026-11-19). A security review is not recorded as done.
- **A skill.** It's the wrong shape for retrieval.
- **UTCP.** There's no existing third-party API to describe.

### Cost (measured, Steps 4 and 5)

On the guarded path: about 11K tokens per one-lookup question and 71K per multi-part question, counting all chat-model tokens. Against the in-app tool, that's about 1.2x the total tokens for a single lookup and about 2.8x for a multi-part question. In return, the caller's context is 4–6x smaller. The guarded path takes 2.5–4.5x the time, and the top of that range is partly our sequential harness (see Finding 2). Starting the stdio server costs about 2 s per session. The hosted service's cost isn't measured yet.

### Switch Conditions

1. **Move to Code Mode** when, over a calendar month of real use, the guarded server's audit log shows either:
   - a **median above 40K model tokens per retrieval loop**, or
   - **more than 25% of loops needing a 4th model turn**.

   The log records `server_model_tokens` and `server_model_turns` per call, so this can be checked on real traffic, not only in the harness. The thresholds apply per retrieval loop (one sub-question), not per client request. Today a loop costs about 8–9K tokens in 2 turns for one lookup, and about 20K in about 3 turns per sub-question on several lookups. The two conditions act as one trigger. Every 3-turn run so far cost at most 27K and every 4-turn run cost 42–44K, so 40K sits just under the 4-turn cost.

   This trigger no longer waits on sandbox approval: the owner states a sandbox is already approved (owner, 2026-11-19). A security review of running model-written code is still not recorded as done, so it is still needed before Code Mode runs.

   **Budget:** tokens per question is the cost proxy, reviewed monthly. The dollar figure will come later, from the API bill.
2. **Widen beyond the Service Desk** when the sign-in, per-unit filtering and deny tests pass.
3. **Drop the MCP route** if no Claude user calls it within a quarter of launch. The audit log counts this.

### Open

The ingress route to the privately hosted service, and the data sign-off for real tickets. These are the same open items as in `ecosystem.md`.

Two more items were opened on 2026-11-18. The owner answered both on 2026-11-19. What is still open is stated under each.

1. **Sandbox approval.** The owner states a sandbox is already approved (owner, 2026-11-19). That is the owner's statement, recorded as given: no approver and no approval date were given, and none is recorded here. The Code Mode trigger no longer waits on sandbox approval. Still open: a security review is not recorded as done.
2. **A seconds trigger.** The switch conditions have token and turn thresholds and no time threshold. The guarded tool took 41.1 s (median, `use_case/evals/tc5_measure_graded_2026-11-18_run{1,2,3}.jsonl`) and 46.7 s (median, `use_case/evals/tc5_measure_run{1,2,3}.jsonl`) on the several-lookups request. The Technology Support Associate defers the acceptable answer time to the owner (owner, 2026-11-19). The owner sets the seconds threshold. Still open: the number is not yet set, so the switch conditions still have no time threshold.

### What the Room Raised

**"Putting Claude in front of the system of record needs a middleware layer, not a direct connection."** The architecture row is that layer: a **gated, read-only tools service between Claude and the system of record**, with **per-caller scoping**. SSO identity maps each caller to a role. A versioned policy table decides which tools and business-unit rows that role can reach, with default deny. The service reaches the system of record through its own least-privilege, read-only service account. No model holds a credential, and no caller sees rows outside its scope.

**"Lead with one ticket."** This shapes the Loom. It opens on a single real-shaped ticket end to end, then shows the measured numbers.

**"The policy cleanup is the product."** Agreed. This week the standard moved to v0.5 with six role and routing rulings closed by their owners, each now in code ([`decisions.md`](decisions.md#owner-decisions-2026-11-10)).

**"Prove onboarding first, then role changes."** Re-hires, transfers and promotions now go straight to a person with the gaps listed, and so does any other exception. Removing stale access is on the list after go-live.

**"Take the name question to the owner."** The owner ruled a legal surname is required. Unnecessary asks on recommended tickets went from 8 to 0. That drop is the relabel: the 8 tickets now carry the label the TC4 agent already gave.

**"Score three multi-turn scenarios."** Built and run live: 3 of 3 pass (surname supplied then recommended, re-hire to review, mirror refused).

**"Report unnecessary asks beside over-grants."** Now a column. The line the CTO hears today: 0 over-grants in 3 recommendations and 0 unnecessary asks, on 29 test tickets (`evals/real_v05/results/endpoint_test.json`).

---

## Steps 1, 7 and 8: Status

- **Step 1:** marks confirmed 2026-11-09 and recorded in `decisions.md` (two fair, one open). The Step 6.2 open question (middleware) is answered by the architecture row above.
- **Step 7:** Service Desk session held 2026-11-09 with the Technology Support Associate. Answers are in `stakeholders.md` and `decisions.md`. The Step 7.2 line is recorded in `decisions.md`.
- **Step 8:** `README.md` "Bring it to work" / TC5 updated 2026-11-09: Desktop use confirmed, hosting route settled and CTO-approved, real volume added.
- **Docker:** image rebuilt 2026-11-10 from this branch. It runs non-root (UID 1000), has no `.env` in the image, mounts the data and the standard read-only, and `/health` returns ok on `anthropic/claude-sonnet-5-5`. Live model calls ran in the container with the key supplied at runtime:
  - The app answered two role questions with cited sources.
  - The MCP server over stdio listed only `answer_onboarding_question`, answered with a citation, declined the password question with no sources, and rejected `search_hybrid` as an unknown tool.
  - On v0.5, a synthetic Massage Therapist ticket was recommended Personal Trainer/Pro New plus the Massage Therapist group at the club, and a synthetic ticket asking for two systems outside every role's bundle went to review as an exception naming both systems and the approver.

---

## Known Issues

- **Grid over-access, 2 of 180:** synthetic tickets where the intake corrects the venue. Next rule: a venue correction goes to a person.
- **Cautious identity calls, 2 real test tickets** (and 1 on dev): sent to a person as conflicting identity where the label recommends. Safe direction; the next failure-analysis target.
- **Decline flag on the app path (re-measured 2026-11-12; risk still open).** On 2026-11-10, in the Docker container, the password question was always refused in the answer text, but `declined` was set in only 1 of 5 runs. The MCP path, which wraps the same `qa.answer_question`, declined cleanly. That points to variation in the model's wording, not a path bug. The code fixes the mechanism: `declined` comes back false only when the reply has no `CANNOT ANSWER:` line, the turn budget didn't run out, and it cites a real page. So the misses were prose refusals that cited a page. On 2026-11-12, run locally (not in Docker) through `qa.answer_question` on `openrouter/anthropic/claude-sonnet-5-5`, 10 of 10 runs declined with no sources. The last 5 are in [`evals/tc5_decline_rerun_2026-11-12.jsonl`](evals/tc5_decline_rerun_2026-11-12.jsonl). No decline code changed in between, so this is a better run, not a fix: the flag still depends on the model writing that line. A keyword filter is not the fix, because it misses paraphrases and declines real tickets about logins. Next Steps item 7 tracks the code fix. **Update 2026-11-12:** the code fix is in. `declined` is now read from the model's final tool call (`answer` or `decline`), forced where the model accepts it and otherwise asked for once more, and prose after that declines; a test runs one decline in five wordings. Measured live (3 runs): the flag follows the call every time, but q10 slipped 2 of 3 on `agentic_hybrid` because the model refused inside the `answer` call. No credential was produced. A rule that declines credential questions before the model runs is the follow-up.
- **Senior Group Fitness Instructor carries staff admin.** Recommended as the NY SOP under an owner exception, with a warning on each recommendation, until the cleanup with stakeholders.
- **Not held out.** Test numbers are "same tickets, current agent". A fresh held-out set is the gate before production.

## Next Steps (production target: end of month)

1. Host the onboarding app container in the cloud, on the same private route as the tools server (SSO sign-in, one group, secrets in a vault).
2. Scope read-only API users for production.
3. Deploy the MCP server to production.
4. Prove writes on the TEST environment before any production write.
5. Monitored rollout: role by role, every action logged to a Teams channel via webhook, weekly email report.
6. Before go-live: remove staff admin from Senior Group Fitness Instructor with stakeholders, security sign-off, and a fresh held-out ticket set.
7. *(Code fix done 2026-11-12: an `answer`/`decline` tool call, forced where supported, else one retry; the eval-set paraphrases are still open.)* Make the decline flag independent of the model's wording. Require a structured decline, either a forced tool call or a required `declined` field, and add a code check that a reply whose text refuses can't come back `declined: false`. Add paraphrased credential questions to the eval set, so a prose refusal shows up as a failure.

---

## Corrections after review, 2026-11-18

The course reviewer raised three wording problems in this write-up. All three were checked against the saved run files and are true. For items 1 to 3 no model was called and no run was repeated: every number in them is read from a file already in the repo. Item 4 was added later the same day and did call the model. The original claims are listed here so they are not silently rewritten.

1. **The headline mixed a relabel with an improvement.**
   - *Was:* "14 → 27 right, over-access 2 → 0" in the TL;DR, the results table, `README.md` and the deck.
   - *Now:* on current labels, 22 to 27 of 29 right. 14 of 29 stays as the TC4 baseline, with a plain statement that the relabel accounts for the move from 14 to 22.
   - *Why:* `python3 use_case/evals/run.py --committed` scores the saved TC4 outputs (`evals/real_v03/results/endpoint_test.json`) at 14 of 29 on the labels at run time and 22 of 29 on the current labels. So 8 of the 13 tickets in "14 to 27" come from the owner's surname ruling changing the labels, and 5 come from the agent and standard v0.5.
2. **"Zero over-access" had no denominator.**
   - *Was:* "over-access 2 → 0", with no count of recommendations.
   - *Now:* 0 over-grants in 3 recommendations (TC4: 2 in 5).
   - *Why:* in `evals/real_v05/results/endpoint_test.json` 3 of the 29 rows have an `actual` status of `recommended`, and all 3 have a `recommended` label. A zero over 3 recommendations is weak evidence on its own, and the write-up now says so.
3. **Unnecessary asks read 1 in two places and 0 in two others.**
   - *Was:* 1 in the results table and in "The line the CTO hears today" (and in the deck); 0 in "Take the name question to the owner" and in `README.md`.
   - *Now:* 0 everywhere.
   - *Why:* `evals/real_v05/results/endpoint_test.json` records `unnecessary_asks` count 0 in `meta.metrics`, and counting its rows gives 0 under the definition in `evals/harness.py`. It is also 0 under a wider reading (any ask where the label does not ask). The 1 could not be reproduced from any saved file, so it is withdrawn, not explained. The two zeros that were already in the text are different measurements that happen to agree: one is the saved TC4 outputs rescored after the relabel, the other is the TC5 run.

Also changed for the same reason: the dev row now shows the saved TC4 dev outputs on current labels (26 of 29) next to the baseline, the same result line in `decisions.md` carries a dated correction, and the deck (`demo/tc5_demo.html`) has the corrected headline, table row and CTO line. The Loom was recorded on 2026-11-10 and still says the original headline.

4. **The several-lookups answers were not graded** (added later on 2026-11-18, with model calls).
   - *Was:* "The several-lookups answers were not graded." The harness checked content only on the one-lookup request and the run files kept no answer text, so nothing showed whether the guarded tool's extra cost bought right answers.
   - *Now:* `measure_tc5.py` saves the final answer text in every row and scores the several-lookups answer on six facts with `tc5_facts.py`. The request was run again 3 times per way (9 runs, same model and settings, no retries needed). Every way scored 6 of 6 in every run. See [Real size](#real-size) and the answer checks under it.
   - *Why it matters:* the extra cost did not buy extra right answers at n=3, so the decision is stated as a trade for the guards and a smaller caller context, not for accuracy. The 2026-11-07 run files are unchanged.

Items 1 to 3 used no model call. Item 4 is the only one that did.
