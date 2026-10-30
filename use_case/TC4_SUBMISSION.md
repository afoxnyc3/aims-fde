# TC4 submission (in progress)

**Status:** Steps 1 to 3 are drafted. `failures.md` was read by Claude and has not been confirmed by Alex yet. There is no `baseline.json`, so the numbers below are a first measurement, not the baseline later weeks are held to.

## Step 1: the taxonomy and the hand scores

[`evals/failures.md`](evals/failures.md) ranks what went wrong in 51 traces: **21 carried at least one failure**, 17 if the truncated decline reason is left out. The 51 traces are 21 distinct inputs.

`evals/human_scores.jsonl` is not written yet. It has to be Alex's own pass/fail, because the judge's agreement is measured against a human.

## Step 2: model-free scorers, echo and oracle

Each cell is the mean over the cases that scorer actually tests, with that count in brackets. There are 20 cases: 15 questions and the 5 settled goldens. DEMO-006 is left out because its golden is an open policy question.

| System | correct_behaviour | gold_cited | reason_intact | flag_honest | caveat_present |
| --- | --- | --- | --- | --- | --- |
| echo | 0.00 (20) | 0.00 (12) | n/a (0) | 0.00 (15) | 0.00 (1) |
| oracle | 1.00 (20) | 1.00 (12) | 1.00 (3) | 1.00 (15) | 1.00 (1) |
| endpoint | 0.85 (20) | 0.75 (12) | 0.33 (6) | 1.00 (15) | 0.00 (1) |

**`correct_behaviour` on the endpoint: 0.85, 95% CI [0.70, 1.00], n=20**, one run on 2026-10-30 with `openrouter/anthropic/claude-sonnet-5.5`. It missed q11, q13 and q14.

What these numbers do not show:

- **The interval is wide.** Twenty cases cannot show a small improvement.
- **The scorers are substring and field checks.** q15 passes `correct_behaviour` while overclaiming (`failures.md` line 3). Lines 3 and 6 need the judge in Step 3, and line 4 has no scorer.
- **One run is a sample of one.** `flag_honest` reads 1.00 here and 44 of 45 on the traces, because q10 returned `declined: false` on one of its three traced runs. `reason_intact` scored 0.00 on an earlier run of the same code path and 0.33 on this one, because how many reasons reach the 300-character cut varies. Its denominator is also only the questions the endpoint happened to decline.
- **Only `correct_behaviour` is safe to compare across runs.** The table above uses each scorer's real denominator, and the saved run's raw means do not. See "What is safe to compare between runs" below.
- **The question oracle carries the labels' terms.** Its answers in `evals/oracle_answers.json` were written by Claude from the labels and the records. They prove the scorers accept a right answer containing those terms, not one in other words.

## Step 3: the judge

**Decision: separation passed, agreement not checked yet. Used for the `grounded` column only, not the headline.**

The rubric is `GROUNDED_RUBRIC` in [`evals/harness.py`](evals/harness.py), for `failures.md` lines 3 and 6: is every claim in the answer stated by the records? The judge is `openai/gpt-5.6-luna`, not the Sonnet model it grades.

| Test | Result |
| --- | --- |
| `Judge.calibrate()` against "The answer is 42." | Good 1.00, wrong 0.00, n=8 |
| Echo and oracle | Echo 0.00, oracle 0.87, n=15 |
| Dev pairs, one unsupported claim added (3 repeats) | Good 1.00, bad 0.08, n=8 pairs. p1 got through on 2 of 3 repeats |
| Holdout pairs, written after the model and rubric were first chosen (3 repeats) | Good 1.00, bad 0.00, n=10 pairs. The rubric's wording was changed twice after that, using these results among others |
| Agreement with hand scores | **Not checked.** Needs `human_scores.jsonl` |

What these results do not show:

- **`calibrate()` passing is close to meaningless here.** `gpt-4.1-mini` also scored 1.00 and 0.00 on it, then missed 5 of the 8 dev pairs. That is why the model changed.
- **The pairs are easier than real traces.** The holdout stayed perfect through every rubric version, including one that missed real failures, so it cannot be the evidence on its own.
- **Verdicts on real traces are not stable.** Over five repeats, q05 run 3 failed every time and q02 and q06 passed every time, but q15 run 3 and q04 runs 1 and 2 split. One pass over the 45 traces flagged 12, against the 4 that lines 3 and 6 count, and how many of the other flags are real is unmeasured. The rubric was tuned against Claude's own reading of those traces, not a human's.
- **Line 4 is not covered.** "No ticket shows this" needs the whole corpus, and the judge sees only the standard and the cited pages.
- **The judge rejects some correct answers.** The oracle's written answers score 0.87, not 1.0. Over three repeats q01, q11 and q14 flipped, so this is the judge's false-reject rate, not a fault in those answers. It is the main reason `grounded` is not the headline.

**Where the text goes.** The judge sends the standard and every cited ticket to its provider, through OpenRouter. That is fine for the synthetic corpus and not yet approved for real tickets, so `harness.py` refuses any other `CORPUS_PATH` unless `JUDGE_CORPUS_APPROVED=1` is set. It keeps the app's `LLM_API_BASE`, so behind a gateway that will not serve this model it fails calibration and stops.

**Cost, measured:** an echo-and-oracle run made 46 judge calls (16 to calibrate, 15 per system) and used about 56k tokens. A full run adds 15 more. At the looked-up price of $0.20 / $1.20 per million tokens, those 46 calls cost about $0.02.

## What is safe to compare between runs

**Compare `correct_behaviour` only.** `helpers.harness` has no way to skip a case, so the raw means in a saved run count vacuous passes, and `compare()` reads the raw means. A single case flipping still clears the 0.02 tolerance while there are fewer than 50 cases, so a regression on a whole case shows, but the other columns are diagnostics, not gates. A single judge wobble is also 0.05, so a `compare()` REGRESSION on `grounded` alone needs reading before anyone believes it. The `grounded` column's name carries a hash of the judge's model and rubric, so `compare()` refuses a run that changed the judge.

## How to run it

See the top of [`evals/run.py`](evals/run.py). `--no-endpoint --no-judge` runs echo and oracle with no model calls. [`evals/calibrate_judge.py`](evals/calibrate_judge.py) runs the separation and agreement tests.
