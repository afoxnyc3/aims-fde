# What goes wrong

> **Read by Claude on 2026-10-30. Alex ruled on 2026-11-03** on line 3 (stands),
> line 4 (a failure: the answer asserts something false about the records), q04
> run 2 (counts under line 6), q04 run 3 (does not count) and DEMO-006 (stays
> out). The traces were found by one read by Claude, except q04 run 2, which a
> judge flag surfaced and Alex ruled in. Lines 1, 2, 5 and 7, and line 6's q05
> run 3, rest on that read alone.
>
> **The judge rubric is not yet aligned with these rulings** (q04 run 3, the q15
> hedges). Revisit `GROUNDED_RUBRIC` before any agreement check.

**22 of 51 traces carried at least one failure; 18 if line 1 is left out,
because it damages the wording of an otherwise correct decline.**

The 51 traces are `collect_traces.py` run on 2026-10-30 against the Week 3
endpoint, answer model `openrouter/anthropic/claude-sonnet-5.5`: 15 questions
three times each, and 6 goldens once each. That is 21 distinct inputs, so the
counts are not 51 independent observations. A trace can carry more than one
failure, so the lines add up to more than 22. The traces stay in
`use_case/data/traces/`, which is gitignored.

Rows are ranked by count. The `#` is a stable ID, not the rank: `harness.py` and the write-ups cite lines by it, so it does not change when a count does.

| # | Traces | What goes wrong | Where | Scorer |
| :---: | :---: | --- | --- | --- |
| 1 | 12 | The decline reason is cut at 300 characters, mid-word. 12 of the 17 declines lost their ending, and q14 run 2 stops at "routed to `human_review` rather tha", just as it reaches the useful part. | q03, q11, q12, q13, q14 | `reason_intact` |
| 2 | 9 | The endpoint declines a question the status rule routes to human review, so the associate gets no answer and no sources. The reason text often knows the routing, but `answer` is empty. | q11, q13, q14, every run | `correct_behaviour`, `gold_cited` |
| 3 | 3 | The answer says a Level 3 trainer gets "the same access as any other Personal Trainer". The standard only lists no separate access by level, and "same access at every level" is an unratified open question. On q03 the endpoint declines to infer this. | q15, every run | `grounded` judge |
| 4 | 2 | The answer says none of the tickets it found has matching employee and manager emails. The corpus has 11, and run 2 of the same question found two. A search that came up short reads as a fact about the records. The right answer is "I found none", not "there are none" (Alex, 2026-11-03). | q07, runs 1 and 3 | none yet. The judge cannot see the whole corpus, and `GROUNDED_RUBRIC` exempts reporting what the search did or did not find. **Week 5 follow-up:** a phrase scorer for "there are none" against "I found none" |
| 6 | 2 | The answer makes a claim no record makes. On q05 it gives a next step no record states ("you would need to check the club-management system itself"), though the answer rule only allows a next step a record states. On q04 it describes a record as something it is not: the status rule is called an "unratified draft" when the record says provisional. | q05 run 3, q04 run 2 | `grounded` judge, which split on q04 run 2 across repeats |
| 5 | 1 | A refusal comes back with `declined: false`, and with unrelated records cited, including another employee's lockout ticket. | q10, run 3 | `flag_honest` |
| 7 | 1 | The start date is corrected from the later comment, but no caveat says it differs from the ticket title. The golden expects one. | DEMO-001 | `caveat_present` |

## Where my own criteria were less consistent than I assumed

- **q15 passes its label and fails line 3.** Its `expected_terms` ask for the
  login at all clubs, and every run has that. The sentence that overclaims is
  beside it, and a substring check cannot see it.
- **Line 3 stays at 3 (Alex, 2026-11-03).** Runs 1 and 3 of q15 hedge beside the claim, saying the list gives nothing specific to Level 3. A hedge next to a wrong claim does not make the claim right, so all three runs count. The judge disagrees on two of them: over five repeats it passed run 1 every time and split on run 3, while it failed run 2 on four of five.
- **The judge flagged two things the first read did not count (ruled by Alex, 2026-11-03).** q04 run 2 calls the status rule an "unratified draft" when the record says provisional: that misdescribes a record, so it counts under line 6. q04 run 3 tells the reader to "check the ticket for other flags first", which no record states: harmless advice, not counted. **Open:** `GROUNDED_RUBRIC` tells the judge to fail any next step no record states, so it will still fail q04 run 3, and the agreement check will count that as a judge error. Either the rubric gets the rule that separates q04 run 3 from q05 run 3 written into it, or the hand score follows the rubric. The line 3 ruling has the same gap: the rubric's only score-1 example is a hedged answer, which pushes the judge to pass q15 runs 1 and 3. Changing the rubric changes the `grounded` fingerprint.
- **DEMO-006 is not counted (confirmed by Alex, 2026-11-03).** The output matches the golden, but the golden is
  an open policy question, so it is not a settled scoring target. It stays out of
  the scored cases until that decision is made.
- **The goldens run a different standard from the questions.** `solve()` uses the
  demo standard, where Hospitality Associate is a role. The question endpoint
  uses draft v0.1, where it is a legacy name for Front Desk Associate. Both are
  right for their own standard, so an answer from one must not be scored against
  the other.

## Not failures, but worth saying

- Question latency ran from 7 to 33 seconds with four requests at once. Nothing
  here sets a budget, so it is not counted.
- `rationale` and `jira_comment` were identical on four of the six goldens. That
  is the open item in `decisions.md`, not something these traces can settle.

## Real tickets: the real_v03 test split and the grid

**Separate from the 51 question traces above.** These are the triage endpoint's
misses on the real_v03 labels, from the committed runs in
[`real_v03/results/`](real_v03/results/) (standard v0.3, intake only,
2026-11-03). The headline in `decisions.md` (row 4 / Step 6) is scored here.
Counts and ticket IDs only; the ticket text stays private. The `R` IDs are
stable, like the numbers above.

**Test split: 15 of 29 tickets missed; 2 of them over-access.** Ranked:

| # | Tickets | What goes wrong | IDs | Scorer |
| :---: | :---: | --- | --- | --- |
| R1 | 10 | Asks for `person_name` (`needs_information`) where the label expects a decision; 8 of the 10 tickets have a blank name field and identify the person only by their email address, 1 (TKT-155) gives a name and is still asked, and 1 (TKT-451) has neither a name nor an email. 8 were expected `recommended` and 2 `human_review` (exception), and one of those 2 also asked for the venue. The cause is the `standard_v02` code module as merged in #41 (not the v0.2 standard), which asks for the name whenever extraction leaves it empty. | Expected `recommended`: TKT-164, TKT-206, TKT-221, TKT-263, TKT-265, TKT-451, TKT-502, TKT-83. Expected exception: TKT-414, TKT-155 | `status_accuracy` |
| R2 | 2 | **Over-access.** Recommends access where the label is `human_review` (exception). This is the failure that gates promotion. | TKT-63, TKT-408 | `no_over_privilege` |
| R3 | 2 | Sends to human review as `ambiguous_identity` where the label expects `recommended`. A cautious miss. | TKT-334, TKT-390 | `status_accuracy` |
| R4 | 1 | Asks for the venue where the label is `human_review` (exception). | TKT-421 | `status_accuracy` |

**Grid: 12 of 180 missed, 11 of them over-access** (GRID-178, awaiting a ruling, left out). The
grid's ticket text is synthetic, but only IDs are listed here to match the
test split. 4 of the 11 are in the grid's test half (GRID-002, GRID-008,
GRID-010, GRID-118). By cause:

| # | Tickets | What goes wrong | IDs |
| :---: | :---: | --- | --- |
| R5 | 6 | A clean-looking ticket for a mapped login role at a club with no pool is recommended. The label is `needs_information` (`venue_confirmation`): confirm the location with the manager. | GRID-002, GRID-003, GRID-005, GRID-007, GRID-008, GRID-010 |
| R6 | 3 | The intake corrects the venue, and the endpoint recommends instead of routing the exception to `human_review`. | GRID-117, GRID-118, GRID-119 |
| R7 | 2 | A v0.3 venue rule the endpoint does not implement yet: a venue-restricted role at another club (label `human_review`, `ambiguous_mapping`), and a lifeguard at a club without a pool (label `needs_information`). | GRID-179, GRID-181 |
| R8 | 1 | An out-of-scope business unit asks for the venue (`needs_information`) where the label is `human_review` (`out_of_scope_business_unit`). Not over-access. In the test half. | GRID-158 |

R5 and R7's lifeguard case are the same pool rule seen from two directions,
so a fix for one should be checked against the other.

**Pool rule implemented (2026-11-08; the `pool_clubs` keys are in v0.3 and v0.4 alike).** The v0.2 decision code now asks for
`venue_confirmation` when a Lifeguard or Aquatics Lead is at a club not in `pool_clubs`; a flagged re-hire,
transfer or promotion goes to review with the gap listed instead. Replaying only that rule over the saved
grid outputs (offline, no model calls) moves the 7 R5/R7 missed asks to 0 of 180, with unnecessary asks
still 0. That is a replay of saved outputs, not a re-run, and the committed TC4 numbers are unchanged.

