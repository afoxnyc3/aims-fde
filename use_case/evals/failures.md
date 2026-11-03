# What goes wrong

> **Read by Claude on 2026-10-30; Alex's rulings applied on 2026-11-03:** line 3
> stands, q04 run 2 counts under line 5, q04 run 3 does not count, and DEMO-006
> stays out. Line 4 has not been ruled on. Every count comes from one read of the
> traces, so Week 5 can still correct it.

**22 of 51 traces carried at least one failure; 18 if line 1 is left out,
because it damages the wording of an otherwise correct decline.**

The 51 traces are `collect_traces.py` run on 2026-10-30 against the Week 3
endpoint, answer model `openrouter/anthropic/claude-sonnet-5.5`: 15 questions
three times each, and 6 goldens once each. That is 21 distinct inputs, so the
counts are not 51 independent observations. A trace can carry more than one
failure, so the lines add up to more than 22. The traces stay in
`use_case/data/traces/`, which is gitignored.

| # | Traces | What goes wrong | Where | Scorer |
| :---: | :---: | --- | --- | --- |
| 1 | 12 | The decline reason is cut at 300 characters, mid-word. 12 of the 17 declines lost their ending, and q14 run 2 stops at "routed to `human_review` rather tha", just as it reaches the useful part. | q03, q11, q12, q13, q14 | `reason_intact` |
| 2 | 9 | The endpoint declines a question the status rule routes to human review, so the associate gets no answer and no sources. The reason text often knows the routing, but `answer` is empty. | q11, q13, q14, every run | `correct_behaviour`, `gold_cited` |
| 3 | 3 | The answer says a Level 3 trainer gets "the same access as any other Personal Trainer". The standard only lists no separate access by level, and "same access at every level" is an unratified open question. On q03 the endpoint declines to infer this. | q15, every run | `grounded` judge |
| 4 | 2 | The answer says none of the tickets it found has matching employee and manager emails. The corpus has 11, and run 2 of the same question found two. A search that came up short reads as a fact about the records. | q07, runs 1 and 3 | none: the judge cannot see the whole corpus |
| 5 | 2 | The answer states something no record states. It gives a next step no record states ("you would need to check the club-management system itself"), though the answer rule only allows a next step a record states. Or it describes a record as something it is not: the status rule called an "unratified draft" when the record says provisional. | q05 run 3, q04 run 2 | `grounded` judge |
| 6 | 1 | A refusal comes back with `declined: false`, and with unrelated records cited, including another employee's lockout ticket. | q10, run 3 | `flag_honest` |
| 7 | 1 | The start date is corrected from the later comment, but no caveat says it differs from the ticket title. The golden expects one. | DEMO-001 | `caveat_present` |

## Where my own criteria were less consistent than I assumed

- **q15 passes its label and fails line 3.** Its `expected_terms` ask for the
  login at all clubs, and every run has that. The sentence that overclaims is
  beside it, and a substring check cannot see it.
- **Line 3 stays at 3 (Alex, 2026-11-03).** Runs 1 and 3 of q15 hedge beside the claim, saying the list gives nothing specific to Level 3. A hedge next to a wrong claim does not make the claim right, so all three runs count. The judge disagrees on two of them: over five repeats it passed run 1 every time and split on run 3, while it failed run 2 on four of five.
- **The judge flagged two things the first read did not count (ruled by Alex, 2026-11-03).** q04 run 2 calls the status rule an "unratified draft" when the record says provisional: that misdescribes a record, so it counts under line 5. q04 run 3 tells the reader to "check the ticket for other flags first", which no record states: harmless advice, not counted.
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
