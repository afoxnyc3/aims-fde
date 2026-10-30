# TC4 submission (in progress)

**Status:** Steps 1 and 2 are drafted. `failures.md` was read by Claude and has not been confirmed by Alex yet. There is no `baseline.json`, so the numbers below are a first measurement, not the baseline later weeks are held to.

## Step 1: the taxonomy and the hand scores

[`evals/failures.md`](evals/failures.md) ranks what went wrong in 51 traces: **21 carried at least one failure**, 17 if the truncated decline reason is left out. The 51 traces are 21 distinct inputs.

`evals/human_scores.jsonl` is not written yet. It has to be Alex's own pass/fail, because the judge's agreement is measured against a human.

## Step 2: model-free scorers, echo and oracle

Each cell is the mean over the cases that scorer actually tests, with that count in brackets. There are 20 cases: 15 questions and the 5 settled goldens. DEMO-006 is left out because its golden is an open policy question.

| System | correct_behaviour | gold_cited | reason_intact | flag_honest | caveat_present |
| --- | --- | --- | --- | --- | --- |
| echo | 0.00 (20) | 0.00 (12) | n/a (0) | 0.00 (15) | 0.00 (1) |
| oracle | 1.00 (20) | 1.00 (12) | 1.00 (3) | 1.00 (15) | 1.00 (1) |
| endpoint | 0.85 (20) | 0.75 (12) | 0.00 (6) | 1.00 (15) | 0.00 (1) |

**`correct_behaviour` on the endpoint: 0.85, 95% CI [0.70, 1.00], n=20**, one run on 2026-10-30 with `openrouter/anthropic/claude-sonnet-5.5`. It missed q11, q13 and q14.

What these numbers do not show:

- **The interval is wide.** Twenty cases cannot show a small improvement.
- **The scorers are substring and field checks.** q15 passes `correct_behaviour` while overclaiming (`failures.md` line 3). Lines 3, 4 and 6 need the judge in Step 3.
- **One run is a sample of one.** q10 refused correctly here but returned `declined: false` on one of three runs in the traces, which is why `flag_honest` reads 1.00 here and 44 of 45 on the traces.
- **The question oracle is built from the labels.** It proves the scorers accept a right answer containing those terms, not one in other words.

## How to run it

See the top of [`evals/run.py`](evals/run.py). `--no-endpoint` runs echo and oracle with no model calls.
