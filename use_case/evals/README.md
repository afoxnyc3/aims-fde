# Evals

## `golden.jsonl`

Five examples, written by hand, in TC1 Step 7. Five — not fifty, and not
generated.

Each line is one object:

```json
{"input": "...", "output": "...", "why": "what makes this the right answer"}
```

The `why` field is the one that earns its keep. In Week 4 you calibrate an
LLM judge against these, and "why" is what you calibrate it on.

### Why you write these by hand

They are the fixed point of the whole cohort. A model-generated example encodes
what the model already does; a hand-written one encodes what *you* would accept,
which is the only thing worth measuring against.

| Week | What uses this file |
| --- | --- |
| 2 | Seeds for synthetic data generation — your variation axes come from these. |
| 4 | The eval harness scores against them, and the judge is calibrated on them. |
| 6 | Injection regressions get added alongside them. |
| 8 | **The bar.** A fine-tuned open model has to pass the same harness the closed one did. |

Get them wrong now and every number for the next nine weeks is measuring the
wrong thing.

### Writing good ones

- Use **real inputs** from your work, with names and identifiers removed.
- Write the output you would **actually accept**, not an idealized one.
- Include at least one **edge case** and one where the right answer is *"I don't
  know"* or *"escalate this"*. A system that never declines is not calibrated.
- Keep them short enough to read in full during review.


## Current coverage and open decisions

- DEMO-001–005 are the five settled cases; DEMO-006 is an unresolved policy example, not a settled scoring target.
- Open decisions (seed coverage and DEMO-006) are tracked in [decisions.md](../decisions.md#decisions-still-required). The settled login/permission and repeated-trigger policies are recorded in the same log.
- The synthetic [demo standard](../../01_Product_Engineering/challenge/demo_standard.json) strips a trailing `.personal` and uses `example.invalid`. Permissions are inherited through roles; `permissions: []` represents no independent grants, not zero effective permissions.

## `retrieval.jsonl`

Ten real questions from your use case, written in TC3, each labelled with the
record(s) in `use_case/data/synthetic_v1.jsonl` that should answer it — plus
the five your first real user typed. One object per line:

```json
{"question": "...", "gold": ["<record id>", "<record id>"], "kind": "lookup | multi-hop | decline"}
```

`gold` lists **every** record needed, because the measure is complete answers,
not "something relevant came back". At least one question is a `decline` — one
your data cannot answer — so you find out whether the endpoint knows when its
top *k* is the wrong answer.

| Week | What uses this file |
| --- | --- |
| 3 | Scores three or more retrieval techniques against each other. The decision in `decisions.md` cites the numbers. |
| 4 | The retrieval half of the eval harness — recall and completeness, tracked per change. |
| 6 | Injection regressions arrive through retrieved content; these are the questions they must not break. |

### This project's labels

Page names are the corpus ids built by
`01_Product_Engineering/challenge/corpus.py`: `STD-*` for the draft standard,
`SYN-*` for synthetic tickets (a hash of the TC2 `row_id`).

```json
{"id": "q08", "question": "...", "gold": ["SYN-8fff8b", "STD-status-rule"], "kind": "lookup | multi-hop | decline", "expected_terms": ["..."], "why": "...", "origin": "...", "strength": "verbatim | clarification | decision_point", "evidence_tickets": 48}
```

`expected_terms` are what a passing answer must contain; an entry that is a
list means any one of those phrasings. A decline question also sets
`"must_decline": true`, and the scorer reads that field, not `kind`. With it, the
terms are the forbidden phrases: a pass is a refusal that contains none of them.
Without it, a decline line is scored as answerable, so a refusal fails. Substring
terms cannot tell a confident answer from a hedged one; the Week 4 judge can.

**Where the questions come from.** Each question was taken from a JSM ticket
export of about 1,000 tickets (Oct 2025 to Sep 2026), read on a separate machine. Only the
question shape travels: real names became synthetic ones from the matching
`SYN-*` record, and `origin` names the kind of source and the month, never a
ticket. `strength` says how real the wording is:

- `verbatim`: someone wrote it (q01, q03, q10).
- `clarification`: a visible exchange asked it, paraphrased (q05, q06, q07).
- `decision_point`: the ticket fields forced the decision, but no one wrote the
  question; the wording is ours (q02, q04, q08, q09). These are the four to
  replace with a colleague's own words, starting with Step 6.

`evidence_tickets` counts the tickets showing the pattern, not traffic.

**Top-k floor: 3 of the 10 need two records (q04, q08, q09), so top-1 is
ruled out; k is at least 2.** 8 of the 10 carry a name, a title or a club.
In the real export, 51 of 84 substantive question-bearing comments on
onboarding tickets (61%) carry a name, email, title, date or club, which is
the case for keeping a lexical index next to dense search (Session 6,
question 8).

## The Week 4 harness

Technical Challenge 4 adds the files that turn this folder into a harness
every later week runs. `python use_case/evals/run.py` is the whole interface.

| File | What it is | Written in |
| --- | --- | --- |
| `failures.md` | What goes wrong, ranked, with counts — from fifty real traces. Every scorer traces back to a line here | TC4 Step 1 |
| `human_scores.jsonl` | Twenty outputs you scored by hand: `{"input", "actual", "pass", "why"}`. The judge's agreement is measured against these | TC4 Step 1 |
| `harness.py` | Your scorers, `run_eval`, `report`, `bootstrap_ci`, the judge rubric | TC4 Steps 2–3 |
| `synthetic.jsonl` | Generated failures, each with the original, the corruption and its failure mode | TC4 Step 4 |
| `scenarios.py` | Three multi-turn scenarios — goal, `knows`, `success`, `must_not` — one a refusal | TC4 Step 5 |
| `run.py` | Points the harness at your endpoint and prints the report | TC4 Step 6 |
| `baseline.json` | **The run itself**, saved with `helpers.harness.save`. Commit it | TC4 Step 6 |

| Week | What uses these files |
| --- | --- |
| 5 | The demo leads with `baseline.json`'s headline number, and the critique goes after it. |
| 6 | Every guardrail is re-run through `run.py`; the winning attack becomes a permanent case and a new line in `failures.md`. |
| 7 | Three memory tests join `scenarios.py`. |
| 8 | **The bar.** `harness.compare(harness.load("baseline.json"), finetuned)` is the pass/fail — and it refuses if the case set changed. |
| 9 | The harness gates the deploy. |
| 10 | A sampled version runs on live traffic. |
