# TC5: the question endpoint built a second way, and measured (DRAFT)

> Draft 2026-11-07, updated 2026-11-10. Steps 3 to 5 are measured below, and the Step 6 architecture row is
> decided (owner, 2026-11-07). The Step 1 marks are confirmed and the service desk session was held 2026-11-09; the Step 7.2 line is recorded.

## Results after the 2026-11-10 rulings

Same 29 real test tickets as TC4, current agent, standard v0.5. **Not held out:** this split has been read closely, and one check below was added after a test run.

| | TC4 (2026-11-03, v0.3) | TC5 (2026-11-10, v0.5) |
| --- | --- | --- |
| Test, right outcome | 14 of 29 (0.48) | **27 of 29 (0.93)** |
| Test, over-access | 2 | **0** |
| Dev, right outcome | 25 of 29 | **28 of 29**, 0 over-access |
| Synthetic grid | 168 of 180, 11 over-access | **174 of 180, 2 over-access** |

What moved it: six owner and service-desk rulings that closed role mappings and the exception order, a business-unit scope and a title staff group in the decision code, and a deterministic check for systems beyond the role bundle ([`decisions.md`](decisions.md#owner-decisions-2026-11-10); labels and runs in [`evals/real_v05`](evals/real_v05/README.md)).

**Failure analysis.** A morning run showed over-access 2 -> 0. It was luck: the two TC4 over-access tickets went to a person only because their roles were still unmapped. Once mapped, the agent recommended both, and both ask for systems outside the bundle (one for a scheduling app, one for several business systems), which extraction did not flag. The fix is in code, not the prompt: the standard names those systems and any intake that names one is an exception. Validated on dev and the synthetic grid, which it was not tuned on. Remaining: 3 real tickets sent to a person as conflicting identity (the safe direction), and 2 grid tickets where the intake corrects the venue (the next rule).

**Known risk, accepted by the owner.** NY Group Fitness Instructors are recommended Senior Group Fitness Instructor, the current SOP, which carries staff admin. "0 over-access" is measured against labels that accept that SOP. Each such recommendation carries a warning, and the exception ends when the role is cleaned up with stakeholders.

## Step 2: the second way, and why

Walking Session 10's ordering for the question endpoint (`search_hybrid` in a tool loop):

1. **Already an HTTP API at work?** No. The retrieval over the standard and past tickets exists only here.
2. **Does anything outside the codebase need to discover it?** **Yes.** Each stakeholder role in `stakeholders.md` has a seat in the organisation's Claude workspace (`ecosystem.md`, Week 5; project
   owner's statement). Confirmed with the service desk on 2026-11-09: the Technology Support Associate uses Claude Desktop every day, so
   the "yes" holds. They should reach the capability from Claude without importing our code.
   **Second way: an MCP server.**
3. Several calls, or calls that return a lot? Also yes (whole records, several searches): this is why
   **Code Mode is the closest alternative not built.** It would keep the 4 to 8 KB of records per search out of
   every model's context, but the guarded tool already keeps them out of the caller's, and Code Mode means
   running model-written code, which needs a sandbox and a security review we do not have. It becomes the pick
   if the switch condition in the Step 6 row fires (real-size numbers below).

## Step 3: Way 2, running

`01_Product_Engineering/challenge/mcp_server.py`: FastMCP 4.1.6, stdio, two tools behind one switch
(`MCP_TOOLSET`):
- `answer_onboarding_question` (**the shipped default**): the guarded question endpoint. It wraps
  `qa.answer_question`, so declines, citation checks and the no-credentials rule all run inside the server,
  and the caller gets back only the answer, its sources and any decline reason, never raw records.
- `search_hybrid` (`MCP_TOOLSET=search`): the same raw search Way 1 gives its model. Used only for the like
  for like measurement.

Middlewares: `AuditCounter` logs every call's shape (tool, argument keys, response bytes, ms, error class,
whether it reached the capability, and the model tokens the server spent on it; never values or results)
and counts only calls that reached the capability, as Way 1's counter does. `ToolErrorMessages` turns
unknown tools and bad arguments into short messages that never echo input, and an upstream outage into a
fixed `UPSTREAM_UNAVAILABLE` marker. Our measurement client aborts the run on it, the same contract as
Way 1; an outside client such as Claude Desktop does not abort, its model reads the marker. Tests:
`python -m unittest test_mcp_server test_measure_tc5` (18 + 4 tests, offline; they include two overlapping guarded calls that each count only their own model tokens). The guarded tool rejects an empty, blank or over-2,000-character question with a clear "Bad arguments" message before the capability runs. **Docker, checked 2026-11-07:** the image builds,
and `docker run -i ... python mcp_server.py` lists only `answer_onboarding_question` and answered the
one-lookup question (Front Desk Associate) through it.

What the model gets back on a bad request (tested in `test_mcp_server.py`):

| Request | Message to the model |
| --- | --- |
| unknown tool `lookup_team` | `Unknown tool 'lookup_team'. Available tools: search_hybrid.` |
| `{"query": "...", "k": "lots"}` | `Bad arguments for 'search_hybrid': k: Input should be a valid integer, unable to parse string as an integer.` |
| `{"k": "lots"}` | `Bad arguments for 'search_hybrid': query: Missing required argument; k: Input should be a valid integer, ...` |
| guarded tool, `{"question": ""}` (or blank, or over 2,000 characters) | `Bad arguments for 'answer_onboarding_question': question: ...` (rejected before the capability runs; logged, not counted) |
| shipped server, unknown tool `search_hybrid` | `Unknown tool 'search_hybrid'. Available tools: answer_onboarding_question.` |

FastMCP's default validation text echoes the arguments back; ours does not, because arguments can carry ticket text.

Point Claude Code or Claude Desktop at it (`.mcp.json`):

```json
{"mcpServers": {"onboarding-qa": {"command": "uv",
  "args": ["run", "--directory", "<absolute path>/01_Product_Engineering/challenge",
           "--env-file", "<absolute path to .env>", "python", "mcp_server.py"],
  "env": {"CORPUS_PATH": "<absolute path to synthetic_v1.jsonl>",
          "MCP_AUDIT_LOG": "<absolute path>/mcp_audit.jsonl", "MCP_PRELOAD": "1"}}}}
```

The app does not load `.env` itself, so `--env-file` is what gives the server its model and key; without it
every guarded call returns `UPSTREAM_UNAVAILABLE`. The audit log is written only when `MCP_AUDIT_LOG` is set,
so any deployment that relies on it (the counts, and the switch conditions below) must set it.

## Steps 4 and 5: both ways measured

`measure_tc5.py`, `anthropic/claude-sonnet-5-5` called **directly on Anthropic's API** through LiteLLM (no
API base set), not through OpenRouter as in TC3 and TC4, so compare these numbers with earlier weeks' with care; same system prompt and loop limit (6 turns),
3 runs per cell, **medians**. *Measured 2026-11-07.* Real-size rows: `use_case/evals/tc5_measure_run{1,2,3}.jsonl` (written with `--out`; the script's default name is `tc5_measure.jsonl`),
taken after the MCP tool was given **the same description and parameter wording as Way 1's schema** (not byte-identical: FastMCP adds `"default": 4` on `k` and `"additionalProperties": false`; `test_mcp_server` pins that difference). Demo-size
rows and an earlier real-size round, taken before that change, are in `tc5_measure_schema_unmatched_run{1,2,3}.jsonl`.
Way 2 runs against **one warm server session per size**, as Claude Desktop keeps a stdio server alive for a
session. Session start-up is measured separately and is **about 2 s once per session**: this round the server
loads and embeds the corpus before it answers the handshake (`MCP_PRELOAD`), so handshake 1.82 to 1.92 s and the first
`list_tools` call 0.07 to 0.10 s, for both the raw-search and the guarded session (each recorded with its own timing). Earlier
rounds warmed on the first call instead (1.8 to 3.0 s in total; those rounds are not on disk, only this one and the unmatched round are). An earlier version of this harness started a new server for every request,
which put that cost into every row; those numbers are superseded.

**Real size** (whole records, 4 by default; the model sets `k` up to 8, so **4.1 to 8.4 KB per raw-search
response**, run averages). Way 2b is the guarded
tool used the way an outside client would; its *client* tokens are what the caller's model reads, its
*total* adds the tokens the server spends running the retrieval loop inside.

| Request | Way | model calls (client) | capability calls | seconds | tokens (client) | tokens (total) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| one lookup | 1 tool | 2 | 2 | 4.9 | 9,136 | 9,136 |
| one lookup | 2 MCP raw search (warm) | 2 | 2 | 5.6 | 8,991 | 8,991 |
| one lookup | 2b MCP guarded (warm) | 2 | 1 guarded call* | 12.0 | 2,346 | 11,271 |
| several lookups | 1 tool | 3 | 5 | 10.4 | 25,668 | 25,668 |
| several lookups | 2 MCP raw search (warm) | 3 | 5 | 12.1 | 19,498 | 19,498 |
| several lookups | 2b MCP guarded (warm) | 2 | 3 guarded calls* | 46.7 | 4,491 | 71,299 |

\* For 2b, capability calls count calls to the guarded tool; each runs its own retrieval loop with several
searches the client never sees (`server_model_turns` in the audit log), so these cells are not comparable with
the search counts above them.

Per run, several lookups: the tool made 5, 5, 5 searches in 3 turns each; raw-search MCP made 5, 7, 5, and the
7-search run took a 4th turn and cost 42,340 tokens. The guarded server ran 9, 9 and 10 model turns of its own
across 3 to 4 sub-questions (`server_model_turns`, from its audit log).

All 18 real-size runs answered (no decline, by `retrieval.decline_reason` on the final text; for 2b that check reads the client's wording, so a paraphrased decline from the server would have passed it. The harness now also counts the server's own `declined` field (`server_declined`), but these runs predate that, so the 2b "answered" is the weaker text check), and all 9 one-lookup runs named
the expected role (`role_named`, a substring check for "front desk associate", so it would also pass an answer
that names the role to reject it; read at n=9, not as grading). The several-lookups answers were not graded.

**Demo size** (each hit cut to 300 characters; raw search only). **Not like for like:** these rows are from the round before the MCP tool's description was matched to Way 1's, and demo size was not re-run after matching. Read them for the size effect, not to compare the two ways:

| Request | Way | model calls | capability calls | seconds | tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| one lookup | 1 tool | 5 | 7 | 14.0 | 24,310 |
| one lookup | 2 MCP (warm) | 6 | 6 | 14.0 | 23,414 |
| several lookups | 1 tool | 5 | 10 | 15.3 | 30,476 |
| several lookups | 2 MCP (warm) | 6 | 10 | 15.7 | 35,406 |

**Parallel tool calls: yes.** The first turn asked for 1 to 4 tool calls at once (`len(msg.tool_calls)`), so
capability calls usually exceed model calls and the round-trip argument does not apply to this model.

**Findings**
- **Raw search over MCP costs about what the in-app tool costs.** With matched schemas, warm, the medians match
  on searches (2 and 5) and turns. Tokens: 8,991 vs 9,136 on one lookup; 19,498 vs 25,668 on several, where MCP's
  searches happened to return smaller records (4.1 vs 5.5 KB), so that gap is the queries the model chose, not
  the transport. The counts do not match run for run: on several lookups the tool made 5, 5, 5 searches and MCP
  5, 7, 5 (the 7-search run took a 4th turn, 42,340 tokens). In the unmatched round on disk the tool made 6, 5, 7
  and MCP 7, 5, 5. So 7-search, 4-turn runs happen on both paths; whether matching the
  description made them rarer for MCP is unproven at this n. MCP's real cost is about 2 s once per session plus
  a process to own and secure.
- **The guarded tool is subagent-shaped.** The caller's model reads 4 to 6 times fewer tokens (2,346 vs
  9,136; 4,491 vs 25,668), because the records stay inside the server. The total is higher: about 1.2x on one
  lookup, and about 2.8x on several, because the client split the question into 3 or 4 calls and each ran its own
  retrieval loop. It was also slower (12.0 s; 46.7 s). That is not start-up: with the corpus preloaded the
  one-lookup median is 12.0 s, against 10.7 s in the unmatched round where the first question paid for
  loading, so the time is the server's own 2-turn
  model loop running behind the client's 2 turns. The several-lookups time is also our harness's doing: the client asked for
  all three calls in one turn and our measurement loop sends them one at a time. A client that sends them
  together could finish nearer one loop's time if the server runs them concurrently; that is untested, and
  the server's per-call token counter assumes calls do not overlap. It buys a clean
  caller context and the guards, and pays for them in total tokens and time.
- **Demo size does not flatter this endpoint; it breaks it.** At 300 characters the role row is cut off,
  the model searches to the turn limit, only 1 of 12 demo-size runs answered at all, and none named the role.
- **The client cannot see the server's work.** Capability calls are counted by the client loop and by the
  server's `AuditCounter`; they agreed on all 18 MCP rows. No call failed or was rejected in these runs
  (`server_failed` = 0), so the failure path is covered by the unit tests, not by this data. The guarded
  tool's model tokens are only visible from the server's log; the caller's own meter misses about 80 to 95%
  of the cost.
- **Small n:** across rounds, raw-search several-lookups runs ranged from about 19K to 44K tokens, more than 2x,
  driven by whether the model took a fourth turn. Read the medians.

**At 10x volume** (derived from the measured rows, not measured at 10x): cost per question follows **model
turns**, not searches. Each turn re-reads everything gathered so far: in the tool rows 5 searches in 3 turns cost
about 23 to 26K tokens (raw-search MCP's cost 19.4K, with smaller records), while the 7-search runs that needed a 4th turn cost 42 to 44K. On the shipped guarded path a
question costs about 11K tokens (one lookup) to 71K (several), all chat-model tokens included (embedding the question adds a few tokens and is not counted). At the Service Desk's volume of about 5 onboarding or access requests a day (Technology Support Associate, 2026-11-09), 10x is 50 a day, or about 0.55M to 3.6M tokens a day, against the tokens-per-question budget reviewed monthly (Step 6). What changes the slope is per-question cost: doubling the record size would roughly double
the accumulated context, and so the per-turn cost, for the tool and for raw-search MCP; the guarded tool
keeps the records out of the caller's context, and Code Mode would keep them out of every model's context.

**Harness fixes after these runs (code review, 2026-11-08), not re-measured:** the server's per-call token counter is now per call rather than a shared global (the measured calls ran one at a time, so the committed numbers are unaffected); Way 2 now answers non-object tool arguments with a message as Way 1 does (no such arguments occurred in these runs); `HIT_CHARS` is applied only when the server runs, not on import; and the audit log records only known argument names.

## Step 6: the architecture row

Decided by the owner on 2026-11-07, and copied into [`decisions.md`](decisions.md#week-5--architecture-row-tc5).
Roles only: no product or vendor names for the identity provider, vault or host.

*Decision:* expose the capability as tools on a **separate, gated tools service, hosted privately**. It has two
kinds of client: the onboarding app, which calls it as a direct internal API with no model in the path, and staff
using Claude, who reach it over MCP. The guarded `answer_onboarding_question` (built and measured above) is
its first tool.
- **Identity** comes from the organisation's SSO only; no user credentials are stored. SSO groups map to
  roles, and a versioned policy table decides which tools, and which business-unit rows, each role can reach.
  Default deny. Read-only in v1.
- **System of record:** each consumer (the tools service, the onboarding app) has its own least-privilege,
  read-only service account. Secrets live in a vault, reached through managed identity.
- **Rollout:** a Service Desk pilot first; widen when the sign-in, per-unit filtering and deny tests pass.

*Rejected:*
- **Raw search over MCP**, built and measured. With the tool description matched, its median searches and turns
  equal the tool's (one lookup 8,991 vs 9,136 tokens; several 19,498 vs 25,668, the gap being smaller records
  returned, not the transport). It buys reach but hands outside models whole records and skips the guards.
- **Code Mode, until the trigger below fires.** It would keep intermediate records out of every model's context,
  but the guarded tool already keeps them out of the caller's, and Code Mode means running model-written code,
  which needs a sandbox and a security review we do not have.
- **A skill:** the wrong shape for retrieval.
- **UTCP:** there is no existing third-party API to describe.

*Cost (measured, Steps 4 and 5):* on the guarded path, about 11K tokens per one-lookup question and 71K per
multi-part question, all chat-model tokens included. Against the in-app tool: about 1.2x the total tokens for a
single lookup and about 2.8x for a multi-part question, for a caller context 4 to 6x smaller and 2.5 to 4.5x the
time. Starting the stdio server costs about 2 s per session; the hosted service's cost is not measured yet.

*Switch conditions:*
1. **To Code Mode** when a sandbox is approved and, over a calendar month of real use, the guarded server's
   audit log shows either a **median above 40K model tokens per retrieval loop** or **more than 25% of loops
   needing a 4th model turn**. The log records `server_model_tokens` and `server_model_turns` per call, so this
   is checkable on real traffic, not only in the harness. It reads per retrieval loop (one sub-question), not per
   client request: today a loop costs about 8 to 9K tokens in 2 turns for one lookup and about 20K in about 3
   turns per sub-question on several lookups. The two conditions are one trigger: every 3-turn run so far cost at
   most 27K and every 4-turn run 42 to 44K, so 40K sits just under the 4-turn cost. **Budget:** tokens per question
   is the cost proxy, reviewed monthly; the dollar figure comes later, from the API bill.
2. **Widen beyond the Service Desk** when the sign-in, per-unit filtering and deny tests pass.
3. **Drop the MCP route** if no Claude user calls it within a quarter of launch (the audit log counts this).

*Open:* the ingress route to the privately hosted service, and the data sign-off for real tickets (the same
open items as in `ecosystem.md`).

### What the room raised, answered by the row

A reviewer pointed out that putting Claude in front of the system of record needs a middleware layer, not a
direct connection. The row is that layer: a **gated, read-only tools service between Claude and the system of
record**, with **per-caller scoping**. SSO identity maps each caller to a role, a versioned policy table decides
which tools and which business-unit rows that role can reach (default deny), and the service reaches the system
of record through its own least-privilege, read-only service account. So no model holds a credential, and no
caller sees rows outside its scope. Another reviewer's advice to **lead with one ticket** shapes the Loom: it
opens on a single real-shaped ticket end to end, then shows the measured numbers.

## Steps 1, 7 and 8: Status

- Step 1: marks confirmed 2026-11-09 and recorded in `decisions.md` (two fair, one open). The Step 6.2 open question (middleware) is answered by the architecture row above.
- Step 7: Service Desk session held 2026-11-09 with the Technology Support Associate. Answers are in `stakeholders.md` and `decisions.md`. The Step 7.2 line is recorded in `decisions.md`.
- Step 8: `README.md` "Bring it to work" / TC5 updated 2026-11-09: Desktop use confirmed, hosting route settled and CTO-approved, real volume added.
- Docker: image rebuilt 2026-11-10 from main (49faead). It runs non-root (UID 1000), has no `.env` in the image, mounts `/data` read-only, and `/health` returns ok on `anthropic/claude-sonnet-5-5`. Live model calls ran in the container with the key supplied at runtime. The app answered two role questions with cited sources. The MCP server, run over stdio, listed only `answer_onboarding_question`, answered with a citation, declined the password question with no sources, and rejected `search_hybrid` as an unknown tool. Re-checked after the v0.5 changes (image rebuilt from this branch, standard mounted read-only): a synthetic Massage Therapist ticket recommended Personal Trainer/Pro New plus the Massage Therapist group at the club, and a synthetic ticket asking for Zoho and Prospr went to review as an exception naming both systems and the approver. Open finding: through the app, the password question was refused in the answer text every time and no credential appeared, but only 1 of 5 runs set `declined: true` with empty `sources`. The other 4 came back `declined: false` with ticket citations. The decline flag follows the model's output, so it is not yet reliable on this question.
