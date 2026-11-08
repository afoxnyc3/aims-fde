# TC4 submission

**Status (2026-11-08):** Steps 1 to 3 and 5 to 8 are written. The baseline is saved at [`evals/baseline.json`](evals/baseline.json): the endpoint on the real_v03 test split, run once, **14 of 29 (0.48, 95% CI 0.28 to 0.66), 2 over-access** ([Step 6](#step-6-the-baseline)). It stays as that historical run. The owner's name policy (2026-11-07) relabelled 10 tickets, and the same saved outputs rescored offline against the new labels are **22 of 29 on test and 27 of 29 on dev**, over-access unchanged at 2 ([Name policy](#name-policy-2026-11-07)). Steps 1 to 3 below were measured on the synthetic Week 1 to 3 suite (20 cases), not on the real tickets. Still open: `failures.md` has Alex's rulings on lines 3 and 4, q04 and DEMO-006, and its other counts are still Claude's read; `human_scores.jsonl` is not written, so the judge's agreement is unchecked; and there is no detection table for `evals/real_v03/synthetic.jsonl`. The Docker re-check passed on 2026-11-03: image `enterprise-fde-challenge` started with the repo-root `.env`, `/health` returned ok on model `anthropic/claude-sonnet-5-5`, and the chat endpoint answered a live question. That answer did not cite sources, because no corpus is mounted until Week 9. Step 5 (scenarios): **run live on 2026-11-07, 3 of 3 passed** ([Step 5](#step-5-the-scenarios)). The re-hire order (a re-hire skips the ask and goes straight to review with the gaps listed) is **confirmed by the owner 2026-11-07**, and transfers and promotions follow the same rule. For the TC5 failure analysis, start at `test_a_mirror_in_a_comment_rests_on_extraction_alone` in `evals/test_scenarios.py`: a mirror request that arrives in a comment is caught by extraction alone, because the regex backstop reads only the intake text.

## Step 1: the taxonomy and the hand scores

[`evals/failures.md`](evals/failures.md) ranks what went wrong in 51 traces: **22 carried at least one failure**, 18 if the truncated decline reason is left out. The 51 traces are 21 distinct inputs.

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
- **Verdicts on real traces are not stable.** Over five repeats, q05 run 3 failed every time and q02 and q06 passed every time, but q15 run 3 and q04 runs 1 and 2 split. One pass over the 45 traces flagged 12, and lines 3 and 6 now count 5 traces. Two of the judge's flags have since been ruled on by Alex: q04 run 2 counts (it is one of the 5), and q04 run 3 does not. Line 3 counts q15 runs 1 and 3, and the judge disagrees on both: it passes run 1 every time and splits on run 3. How many of the remaining flags are real is unmeasured. The rubric was tuned against Claude's own reading of those traces, not a human's.
- **Line 4 is not covered.** "No ticket shows this" needs the whole corpus, and the judge sees only the standard and the cited pages.
- **The judge rejects some correct answers.** The oracle's written answers score 0.87, not 1.0. Over three repeats q01, q11 and q14 flipped, so this is the judge's false-reject rate, not a fault in those answers. It is the main reason `grounded` is not the headline.

**Where the text goes.** The judge sends the standard and every cited ticket to its provider, through OpenRouter. That is fine for the synthetic corpus and not yet approved for real tickets, so `harness.py` refuses any other `CORPUS_PATH` unless `JUDGE_CORPUS_APPROVED=1` is set. It keeps the app's `LLM_API_BASE`, so behind a gateway that will not serve this model it fails calibration and stops.

**Cost, measured:** an echo-and-oracle run made 46 judge calls (16 to calibrate, 15 per system) and used about 56k tokens. A full run adds 15 more. At the looked-up price of $0.20 / $1.20 per million tokens, those 46 calls cost about $0.02.

## Step 5: the scenarios

Both endpoints answer one ticket or one question and hold no conversation, so the three multi-turn scenarios in [`evals/scenarios.jsonl`](evals/scenarios.jsonl) (synthetic, added 2026-11-06) re-send the same ticket with the follow-up comment appended. SYN-ASK-001: a nameless intake is asked for the name, and the follow-up that gives it turns into a recommendation. SYN-ASK-002: a re-hire with no name goes to `human_review` on turn 1, with the missing name in `review_missing_fields` and the handoff comment, not an ask. SYN-ASK-003: a follow-up that asks to mirror a colleague is refused and routed to review.

**Run live on 2026-11-07: 3 of 3 passed.** The first attempt passed 2 of 3, because of the fixture, not the endpoint: the scenario intakes named demo-only venues ("Venue A", "Venue B") that do not exist in the v0.3 standard. They now name Club A and Club B, and the re-run passed all three. One run each, so this shows the scenarios can pass, not how often.

**A first-name-only probe** (an intake that gives only a first name) gets an ask for the surname. That is now policy (the name policy below), but the code does not enforce it yet: the v0.2 decision code checks only that extraction returned a name, so the ask came from extraction, not from a rule. A deterministic surname check is a follow-up. Whether the club-management system itself rejects an account with no surname is being checked on its TEST environment, for the record.

## Step 6: the baseline

**Headline: `status_accuracy` on the real_v03 test split, run once: 14 of 29 (0.48, 95% CI 0.28 to 0.66). Over-access, which gates promotion: 2 of 29** (TKT-63 and TKT-408, recommended where the label is `human_review`). The decision, what it does not cover and what would change it are in [`decisions.md`](decisions.md) (row 4 / Step 6).

| System | Dev (29) | Test (29) | Grid (180) |
| --- | --- | --- | --- |
| echo | 0.00 | 0.00 | 0.00 |
| oracle | 1.00 | 1.00 | 1.00 |
| endpoint | 0.86 [0.72, 0.97], 0 over-access, 2 unnecessary asks, 0 missed asks | **0.48 [0.28, 0.66], 2 over-access, 8 unnecessary asks (+3 on exception labels), 0 missed asks** | 0.93 [0.89, 0.97], 11 over-access, 0 unnecessary asks, 7 missed asks |

**Unnecessary asks** (added 2026-11-06, read from the saved runs, no re-run): the endpoint returned `needs_information` where the label is `recommended`, an extra round trip rather than a risk. On test, **8 unnecessary asks on recommended labels** (8 of the 13 `recommended` labels at the time; the name policy has since relabelled all 8), **plus 3 on exception tickets**, reported separately because those tickets need a person whatever the requester answers. By their label evidence, two are re-hire tickets (TKT-414 "re-hire"; TKT-155 "re-hire, transfer, promotion/title change") that the re-hire order now routes straight to review; the third (TKT-421, systems beyond the bundle plus a venue correction) is not a re-hire and would still be asked. "Now routes" is the v0.2 code, not a measurement: the saved runs came from the private v0.3 runner, which keeps the old order. So the CTO line was: 2 over-grants, 8 extra round-trips on recommended tickets, and 3 more on exception tickets, 2 of which the re-hire order (confirmed by the owner 2026-11-07) removes. After the name policy the 8 are 0: every one was a ticket with no surname, which the policy sends back to the manager ([below](#name-policy-2026-11-07)).

**Missed asks** (added 2026-11-07, same saved runs; **they gate promotion like over-access**, owner decision 2026-11-07, while unnecessary asks are reported only): the other direction, `recommended` where the label is `needs_information`, so a proposal went out on an intake missing a fact the standard requires. None on dev or test. On grid, 7 of 180, and all 7 skip the same field, `venue_confirmation`: a pool role (Lifeguard or Aquatics Lead) at a club with no pool, which the label sends back to confirm the location with the manager. They are rows R5 (GRID-002, 003, 005, 007, 008, 010) and R7 (GRID-181) in [`failures.md`](evals/failures.md), which records the pool rule as a v0.3 venue rule the endpoint does not implement yet. So the grid's 0 unnecessary asks does not mean its asking is right, only that its errors run the other way, and on one rule. Because missed asks now gate, those 7 block promotion of the pool roles until the pool rule is implemented.

`openrouter/anthropic/claude-sonnet-5.5`, standard v0.3, intake only. Public repo commit `83f2e5d`, but the runner and the v0.3 standard that produced the run are private, so checking out that commit does not reproduce it. The grid leaves out GRID-178, which awaits a ruling.

**Why it is below the demo's 24 of 29:** 10 of the 15 test misses ask for `person_name`. `standard_v02` as merged in #41 asks for the name whenever extraction leaves it empty, and 8 of the 10 tickets have a blank name field and identify the person only by their email address, 1 (TKT-155) gives a name and is still asked, and 1 (TKT-451) has neither a name nor an email. The demo ran on an uncommitted version that filled in a placeholder name, and on standard v0.2, so the two numbers are not like for like.

**Reproducing it.** The real ticket text, the runner and the v0.3 standard stay private, so the run cannot be repeated from this repo. It can be reported and compared, offline:

```
$ python3 use_case/evals/run.py --committed
...
PASS  endpoint_test → endpoint_test  [no_over_privilege +0.000  status_accuracy +0.000]
```

## Name policy (2026-11-07)

**The owner's rule:** a legal surname is required. An intake with no surname goes back to the requesting manager (`needs_information`, `person_name`).

The baseline's unnecessary-ask count exposed the gap. Eight test tickets the labels marked `recommended` were asked for `person_name`, and every one had no surname anywhere in the intake: a blank name field with the person identified only by an email handle, or (TKT-451) neither a name nor an email. The labels said recommend, the endpoint said ask, and nothing written down said which was right. The owner ruled that the endpoint was: the metric did its job, by exposing a policy gap the owner then closed.

**Relabelled in [`evals/real_v03/golden.jsonl`](evals/real_v03/golden.jsonl)** from `recommended` to `needs_information` with `missing_fields: ["person_name"]`, with the policy line added to their evidence: TKT-83, 164, 206, 221, 263, 265, 451, 502 (test) and TKT-406, 427 (dev).

**Rescored offline** from the saved outputs against the new labels (`python3 use_case/evals/run.py --committed`, second table; no model calls, no re-run):

| Endpoint | Before (labels at run time) | After (name policy) |
| --- | --- | --- |
| Test | 14 of 29 (0.48, CI 0.28 to 0.66) | **22 of 29** (0.76, CI 0.59 to 0.90) |
| Dev | 25 of 29 (0.86, CI 0.72 to 0.97) | **27 of 29** (0.93, CI 0.83 to 1.00) |
| Over-access (test) | 2 of 29 (TKT-63, TKT-408) | 2 of 29, unchanged |
| Unnecessary asks on `recommended` labels | 8 test, 2 dev | **0** test, **0** dev |
| Missed asks | 0 test, 0 dev | 0 test, 0 dev |

`baseline.json` is not edited: it stays the 14 of 29 historical run, and `--committed` still checks it against `results/endpoint_test.json` and prints `PASS`. A rescored run carries a new fingerprint, because its expected outputs changed, so `compare()` refuses to set it beside the baseline. The same holds for the next private-runner run on these labels: **the next real run needs a new baseline**, saved beside this one, not compared to it.

**The missed-ask gate is read from the report, not enforced by `compare()`.** Missed asks are counted in the `--committed` table, not stored as a scorer in the run, so a `compare()` PASS does not by itself mean zero missed asks. Making it a scorer changes the fingerprint, so it belongs with the new baseline. What the rescore does not show: the endpoint did not get better, the labels moved to the rule it already followed. The test split has now been read closely twice, so the 22 of 29 is not a held-out number. The 3 asks on exception labels (TKT-414, 155, 421) remain, and 2 of them are re-hires the confirmed re-hire order routes straight to review in the v0.2 code; the saved runs predate that order.

## Step 7: the demo

**Demo, 2026-11-02, to the CTO.** Five minutes on the triage agent over the real test split: 24 of 29 right, 4 sent to a human when they could have been recommended (the cautious kind of miss), and 1 over-granted (a lifeguard who also covers fitness; the matrix has no cross-unit rule). The CTO's questions, in my words (confirmed by Alex, 2026-11-03):

1. **Over-access is the security question.** What stops the agent granting more than the role needs, and how would we know it had? *Answer then:* over-access is scored as its own column, and any case blocks. *What changed:* it is now the gating column in the decision row.
2. **Is this on real tickets?** *Answer:* yes, pseudonymised intake tickets, labelled by IT against the role matrix. Ticket text stays private. Labels and scores are public.
3. **How does it connect to the service desk?** *Answer:* not yet. It reads exported tickets. The JSM read-only service account and the comment-posting path are designed (decisions, Week 1 Step 8) but not built.
4. **Can it remove admin rights from people outside Technology?** *Answer:* out of scope for onboarding. It is a separate clean-up and needs its own approval. Logged as a follow-up.
5. **Can admins sign in with OAuth?** *Answer:* not today. It goes into the integration requirements for the JSM connection.

**Rehearsed with:** the CTO, live, on 2026-11-02. A real person who owns the approval, asking the questions recorded here. Logged in [`stakeholders.md`](stakeholders.md); what it changed is in [`decisions.md`](decisions.md#week-4--what-the-step-7-demo-changed). The figures above are the demo's. Re-scored on the current labels and code, the test split is 14 of 29 (Step 6).

## Step 8: bring it to work

The three swap lines (data, model or endpoint, approval) are under "TC4 — evals" in [`README.md`](README.md#tc4--evals).

## What is safe to compare between synthetic-suite runs

This section governs runs of `run.py` on the 20-case synthetic suite. Those runs cannot be compared to `baseline.json`, which has different cases and scorers (`status_accuracy`, `no_over_privilege`), and `compare()` refuses. **Between synthetic runs, compare `correct_behaviour` only.** `helpers.harness` has no way to skip a case, so the raw means in a saved run count vacuous passes, and `compare()` reads the raw means. A single case flipping still clears the 0.02 tolerance while there are fewer than 50 cases, so a regression on a whole case shows, but the other columns are diagnostics, not gates. A single judge wobble is also 0.05, so a `compare()` REGRESSION on `grounded` alone needs reading before anyone believes it. The `grounded` column's name carries a hash of the judge's model and rubric, so `compare()` refuses a run that changed the judge.

## How to run it

See the top of [`evals/run.py`](evals/run.py). `--committed` reports the real_v03 baseline from the saved runs, offline. `--no-endpoint --no-judge` runs echo and oracle on the synthetic suite with no model calls. [`evals/calibrate_judge.py`](evals/calibrate_judge.py) runs the separation and agreement tests.
