# What goes wrong

> **Draft, read by Claude on 2026-10-30. Alex has not confirmed it yet.** Every
> count below comes from one read of the traces. Week 5 will go after this file,
> so it needs reading against the traces and correcting before it is final.

**21 of 51 traces carried at least one failure; 17 if line 1 is left out,
because it damages the wording of an otherwise correct decline.**

The 51 traces are `collect_traces.py` run on 2026-10-30 against the Week 3
endpoint, answer model `openrouter/anthropic/claude-sonnet-5.5`: 15 questions
three times each, and 6 goldens once each. That is 21 distinct inputs, so the
counts are not 51 independent observations. A trace can carry more than one
failure, so the lines add up to more than 21. The traces stay in
`use_case/data/traces/`, which is gitignored.

| # | Traces | What goes wrong | Where | Scorer |
| :---: | :---: | --- | --- | --- |
| 1 | 12 | The decline reason is cut at 300 characters, mid-word. 12 of the 17 declines lost their ending, and q14 run 2 stops at "routed to `human_review` rather tha", just as it reaches the useful part. | q03, q11, q12, q13, q14 | `reason_intact` |
| 2 | 9 | The endpoint declines a question the status rule routes to human review, so the associate gets no answer and no sources. The reason text often knows the routing, but `answer` is empty. | q11, q13, q14, every run | `correct_behaviour`, `gold_cited` |
| 3 | 3 | The answer says a Level 3 trainer gets "the same access as any other Personal Trainer". The standard only lists no separate access by level, and "same access at every level" is an unratified open question. On q03 the endpoint declines to infer this. | q15, every run | judge (Step 3) |
| 4 | 2 | The answer says none of the tickets it found has matching employee and manager emails. The corpus has 11, and run 2 of the same question found two. A search that came up short reads as a fact about the records. | q07, runs 1 and 3 | judge (Step 3) |
| 5 | 1 | A refusal comes back with `declined: false`, and with unrelated records cited, including another employee's lockout ticket. | q10, run 3 | `flag_honest` |
| 6 | 1 | The answer gives a next step no record states ("you would need to check the club-management system itself"). The answer rule only allows a next step a record states. | q05, run 3 | judge (Step 3) |
| 7 | 1 | The start date is corrected from the later comment, but no caveat says it differs from the ticket title. The golden expects one. | DEMO-001 | `caveat_present` |

## Where my own criteria were less consistent than I assumed

- **q15 passes its label and fails line 3.** Its `expected_terms` ask for the
  login at all clubs, and every run has that. The sentence that overclaims is
  beside it, and a substring check cannot see it.
- **DEMO-006 is not counted.** The output matches the golden, but the golden is
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
