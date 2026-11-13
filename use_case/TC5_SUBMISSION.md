# TC5: The Question Endpoint, Built a Second Way and Measured

> Submitted 2026-11-10 (Known Issues updated 2026-11-12 with a re-measurement; the Loom and deck show the 2026-11-10 state). **Loom:** https://www.loom.com/share/1a3b85c2674d4b27aeb5fd5ce7c89e14 (4 min). **Deck:** [`demo/tc5_demo.html`](demo/tc5_demo.html).
> Architecture row decided 2026-11-07. Step 1 marks confirmed, Service Desk session held and Step 7.2 line recorded on 2026-11-09. Role rulings and the v0.5 re-run on 2026-11-10.

## TL;DR

I exposed the onboarding question endpoint as an MCP server and measured it against the in-app tool. **Transport is not the cost:** raw search over MCP costs what the in-app tool costs. **The guarded tool is what ships.** The caller's model reads 4–6x fewer tokens, and every guard runs inside the server. The price is 1.2–2.8x the total tokens and 2.5–4.5x the time.

**Decision:** a private, gated, read-only tools service. The onboarding app calls it as an internal API. Staff using Claude reach it over MCP.

**And the agent got better.** On the same 29 real test tickets as TC4: **14 → 27 right, over-access 2 → 0** (not held out; see [Results after the 2026-11-10 rulings](#results-after-the-2026-11-10-rulings)). The model barely changed. The standard did.

---

## Results after the 2026-11-10 rulings

Same 29 real test tickets as TC4, current agent, standard v0.5. **Not held out:** this split has been read closely, and one check below was added after a test run.

| | TC4 (2026-11-03, v0.3) | TC5 (2026-11-10, v0.5) |
| --- | --- | --- |
| Test, right outcome | 14 of 29 (0.48) | **27 of 29 (0.93)** |
| Test, over-access | 2 | **0** |
| Dev, right outcome | 25 of 29 | **28 of 29**, 0 over-access |
| Synthetic grid | 168 of 180, 11 over-access | **174 of 180, 2 over-access** |
| Unnecessary asks (test) | 8 | **1** |

**What moved it:** six owner and Service Desk rulings that closed role mappings and the exception order, a business-unit scope and a per-title staff group in the decision code, and a deterministic check for systems outside the role bundle. Rulings in [`decisions.md`](decisions.md#owner-decisions-2026-11-10); labels and runs in [`evals/real_v05`](evals/real_v05/README.md). `real_v03` stays the frozen TC4 record.

**Failure analysis: our first zero was luck.** A morning run showed over-access 2 → 0. The two TC4 over-access tickets went to a person only because their roles were still unmapped. Once mapped, the agent recommended both, and both ask for systems outside the bundle (one for a scheduling app, one for several business systems). Extraction didn't flag either. The fix is in code, not the prompt: the standard names those systems, and an intake that names one becomes an exception. Validated on dev and on the synthetic grid, which it was not tuned on.

**Known risk, accepted by the owner.** NY Group Fitness Instructors are recommended Senior Group Fitness Instructor, the current SOP, which carries staff admin. "0 over-access" is measured against labels that accept that SOP. Every such recommendation carries a warning, and the exception ends when the role is cleaned up with stakeholders.

---

## Step 2: Why a Second Way

I walked Session 10's ordering for the question endpoint (`search_hybrid` in a tool loop):

1. **Is it already an HTTP API at work?** No. Retrieval over the standard and the past tickets exists only in this codebase.
2. **Does anything outside the codebase need to find it?** Yes. Every stakeholder role in `stakeholders.md` has a seat in our Claude workspace (`ecosystem.md`, Week 5, from the project owner). The Service Desk confirmed it on 2026-11-09: the Technology Support Associate uses Claude Desktop every day. Staff should reach the capability from Claude without importing our code. **Second way: an MCP server.**
3. **Many calls, or large responses?** Also yes: whole records and several searches per question. That makes **Code Mode the closest alternative I didn't build.** It would keep the 4–8 KB of records each search returns out of every model's context. The guarded tool already keeps them out of the caller's context. Code Mode also means running model-written code, which needs a sandbox and a security review we don't have. It becomes the pick when the Step 6 switch condition fires.

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

**Startup cost: about 2 s, once per session.** With `MCP_PRELOAD`, the server loads and embeds the corpus before it answers the handshake. The handshake takes 1.82–1.92 s and the first `list_tools` call takes 0.07–0.10 s. That holds for both the raw-search and the guarded session, each timed on its own. Earlier rounds warmed on the first call instead, at 1.8–3.0 s total. Those rounds aren't on disk: only this round and the unmatched round are. An earlier version of the harness started a new server for every request and put that cost into every row. Those numbers are superseded.

### Real size

Whole records, 4 by default. The model sets `k` up to 8, so a raw-search response is **4.1–8.4 KB** (run averages). Way 2b is the guarded tool used the way an outside client would use it. *Client* tokens are what the caller's model reads. *Total* tokens add what the server spends on its internal retrieval loop.

| Request | Way | Model calls (client) | Capability calls | Seconds | Tokens (client) | Tokens (total) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| one lookup | 1 tool | 2 | 2 | 4.9 | 9,136 | 9,136 |
| one lookup | 2 MCP raw search (warm) | 2 | 2 | 5.6 | 8,991 | 8,991 |
| one lookup | 2b MCP guarded (warm) | 2 | 1 guarded call* | 12.0 | 2,346 | 11,271 |
| several lookups | 1 tool | 3 | 5 | 10.4 | 25,668 | 25,668 |
| several lookups | 2 MCP raw search (warm) | 3 | 5 | 12.1 | 19,498 | 19,498 |
| several lookups | 2b MCP guarded (warm) | 2 | 3 guarded calls* | 46.7 | 4,491 | 71,299 |

\* For 2b, capability calls count calls to the guarded tool. Each call runs its own retrieval loop with several searches the client never sees (`server_model_turns` in the audit log). These cells don't compare with the search counts above them.

**Per run, several lookups:** the tool made 5, 5 and 5 searches, in 3 turns each. Raw-search MCP made 5, 7 and 5. The 7-search run took a 4th turn and cost 42,340 tokens. The guarded server ran 9, 9 and 10 model turns of its own across 3–4 sub-questions (`server_model_turns`, from its audit log).

**Answer checks**
- **All 18 real-size runs answered**, meaning none declined according to `retrieval.decline_reason` on the final text. For 2b this check reads the client's wording, so a paraphrased decline from the server would still pass. The harness now also counts the server's own `declined` field (`server_declined`), but these runs predate it. Treat 2b's "answered" as the weaker text check.
- **All 9 one-lookup runs named the expected role.** `role_named` is a substring check for "front desk associate", so an answer that names the role in order to reject it would also pass. Read this at n=9, not as grading.
- **The several-lookups answers were not graded.**

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
- **Code Mode, until the trigger below fires.** It would keep intermediate records out of every model's context. The guarded tool already keeps them out of the caller's, and Code Mode needs a sandbox and a security review we don't have.
- **A skill.** It's the wrong shape for retrieval.
- **UTCP.** There's no existing third-party API to describe.

### Cost (measured, Steps 4 and 5)

On the guarded path: about 11K tokens per one-lookup question and 71K per multi-part question, counting all chat-model tokens. Against the in-app tool, that's about 1.2x the total tokens for a single lookup and about 2.8x for a multi-part question. In return, the caller's context is 4–6x smaller. The guarded path takes 2.5–4.5x the time, and the top of that range is partly our sequential harness (see Finding 2). Starting the stdio server costs about 2 s per session. The hosted service's cost isn't measured yet.

### Switch Conditions

1. **Move to Code Mode** when a sandbox is approved and, over a calendar month of real use, the guarded server's audit log shows either:
   - a **median above 40K model tokens per retrieval loop**, or
   - **more than 25% of loops needing a 4th model turn**.

   The log records `server_model_tokens` and `server_model_turns` per call, so this can be checked on real traffic, not only in the harness. The thresholds apply per retrieval loop (one sub-question), not per client request. Today a loop costs about 8–9K tokens in 2 turns for one lookup, and about 20K in about 3 turns per sub-question on several lookups. The two conditions act as one trigger. Every 3-turn run so far cost at most 27K and every 4-turn run cost 42–44K, so 40K sits just under the 4-turn cost.

   **Budget:** tokens per question is the cost proxy, reviewed monthly. The dollar figure will come later, from the API bill.
2. **Widen beyond the Service Desk** when the sign-in, per-unit filtering and deny tests pass.
3. **Drop the MCP route** if no Claude user calls it within a quarter of launch. The audit log counts this.

### Open

The ingress route to the privately hosted service, and the data sign-off for real tickets. These are the same open items as in `ecosystem.md`.

### What the Room Raised

**"Putting Claude in front of the system of record needs a middleware layer, not a direct connection."** The architecture row is that layer: a **gated, read-only tools service between Claude and the system of record**, with **per-caller scoping**. SSO identity maps each caller to a role. A versioned policy table decides which tools and business-unit rows that role can reach, with default deny. The service reaches the system of record through its own least-privilege, read-only service account. No model holds a credential, and no caller sees rows outside its scope.

**"Lead with one ticket."** This shapes the Loom. It opens on a single real-shaped ticket end to end, then shows the measured numbers.

**"The policy cleanup is the product."** Agreed. This week the standard moved to v0.5 with six role and routing rulings closed by their owners, each now in code ([`decisions.md`](decisions.md#owner-decisions-2026-11-10)).

**"Prove onboarding first, then role changes."** Re-hires, transfers and promotions now go straight to a person with the gaps listed, and so does any other exception. Removing stale access is on the list after go-live.

**"Take the name question to the owner."** The owner ruled a legal surname is required. Unnecessary asks on recommended tickets went from 8 to 0.

**"Score three multi-turn scenarios."** Built and run live: 3 of 3 pass (surname supplied then recommended, re-hire to review, mirror refused).

**"Report unnecessary asks beside over-grants."** Now a column. The line the CTO hears today: 0 over-grants, 1 extra round-trip, on 29 test tickets.

---

## Steps 1, 7 and 8: Status

- **Step 1:** marks confirmed 2026-11-09 and recorded in `decisions.md` (two fair, one open). The Step 6.2 open question (middleware) is answered by the architecture row above.
- **Step 7:** Service Desk session held 2026-11-09 with the Technology Support Associate. Answers are in `stakeholders.md` and `decisions.md`. The Step 7.2 line is recorded in `decisions.md`.
- **Step 8:** `README.md` "Bring it to work" / TC5 updated 2026-11-09: Desktop use confirmed, hosting route settled and CTO-approved, real volume added.
- **Docker:** image rebuilt 2026-11-10 from this branch. It runs non-root (UID 1000), has no `.env` in the image, mounts the data and the standard read-only, and `/health` returns ok on `anthropic/claude-sonnet-5-5`. Live model calls ran in the container with the key supplied at runtime:
  - The app answered two role questions with cited sources.
  - The MCP server over stdio listed only `answer_onboarding_question`, answered with a citation, declined the password question with no sources, and rejected `search_hybrid` as an unknown tool.
  - On v0.5, a synthetic Massage Therapist ticket was recommended Personal Trainer/Pro New plus the Massage Therapist group at the club, and a synthetic ticket asking for Zoho and Prospr went to review as an exception naming both systems and the approver.

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
