# Generator run log

One entry per run. The data stays in `use_case/data/` (gitignored); this file
records what was run and what happened. Newest last.

## 2026-10-18 — small batch, run 1 (`synth_run_20261018_200802`)

- **Scope:** `--role-fit venue_dependent --one-per-cell` (24 rows, 24 cells), seed 42.
- **Model:** `claude-opus-5-5`, Anthropic backend, effort `low`.
- **Temperature:** requested 0.7, **not applied**. The model rejects the parameter (400: "`temperature` is deprecated for this model"), so generation ran at the model's default sampling.
- **Result:** 24 planned, 21 generated, 21 schema-valid, **17 verified**, 7 dead cells.
- **Failure causes:**
  - 3 rows, generator bug: four parallel workers sent `temperature` before the first 400 switched it off, and only the first worker retried. The other three rows were recorded as errors, not generated. Fixed: any request that carried `temperature` retries without it.
  - 3 rows, verifier too strict: notes said "coming back to the company" for `returning`, but the check only accepted the stem `return`. Fixed with an accepted-phrase list.
  - 1 row, real generation failure: a `transferring` row left `previous_location` blank.

## 2026-10-18 — small batch, run 2 (`synth_run_20261018_200858`)

- **Scope, model, temperature:** same as run 1 (temperature not applied).
- **Result:** 24 planned, 24 generated, 24 schema-valid, **24 verified**, 0 dead cells. Dedupe skipped (one row per cell).
- **Read-through notes:** on the contradiction-b row, the model explained the shared email in the notes ("I put mine for now"). Manager names repeated across rows. Both led to the next change set: a no-explanation instruction on contradiction rows, and code-picked names.

## 2026-10-18 — small batch, run 3 (`synth_run_20261018_221801`)

After commit `a2903ae` (code-picked names, membership exclusion, no-explanation instruction on contradiction rows, accepted-phrase list for the intent note).

- **Scope, model, temperature:** same as run 1 (temperature not applied).
- **Result:** 24 planned, 24 generated, 24 schema-valid, **24 verified**, 0 dead cells. Dedupe skipped (one row per cell).
- **Spot check:** none of the 3 contradiction-b rows explains the shared email. The 2 `membership_only` × `changed_after_submission` rows change start date and club, not membership.

## 2026-10-18 — full run (`synth_run_20261018_221844`)

- **Scope:** all 126 rows (102 cells), seed 42. Same model; temperature not applied.
- **Result:** 126 planned, 125 generated, 125 schema-valid, **125 verified**. After dedupe: 125 (0 dropped at Jaccard ≥ 0.85, 0 cross-cell pairs).
- **Dead cell:** `exact|new_hire|internal_contradiction|beyond_template`. Its only row was `schema_invalid` after one retry. The raw model output was not kept, so the cause is unknown.
- **Verified status mix:** 36 recommended / 48 needs_information / 36 human_review / 5 ignored (planned 36/49/36/5).
- **Intent phrases matched:** returning → "coming back" 9, "returning" 7; transferring → "transferring" 16; promoted → "promoted" 16.
- **Dedupe calibration:** highest same-cell Jaccard was 0.43 (mean 0.22, 36 pairs). Code-picked names, emails, and dates are part of the shingled content, so same-cell rows sit far below 0.85. Per the decisions.md rule, this is a signal to lower the threshold or exclude code-picked values from the shingles. Not yet decided.

## 2026-10-18 — full run, repeat (`synth_run_20261018_224510`)

Re-run to fill the dead cell, after `generate.py` started keeping the raw model reply on every failed attempt (`failed_attempts`).

- **Scope, model, temperature:** as the previous full run (temperature not applied).
- **Result:** 126 planned, 125 generated, 125 schema-valid, **125 verified**. After dedupe: 125 (0 dropped; same-cell Jaccard max 0.43, mean 0.21).
- **Dead cell, same as before:** `exact|new_hire|internal_contradiction|beyond_template`. Cause now recorded: both attempts returned `stop_reason: "refusal"` with no content. **This is not a schema failure.**
- **Diagnosis (one extra call per variant, so single samples):**
  - As generated: refused, category `cyber`. That makes 5 refusals in 5 tries across the two runs and this test.
  - Same row without "Do not explain, justify, or acknowledge the inconsistency.": generated normally.
  - Same row with a hardware extra request instead of "access to the marketing email tool": generated normally.
  - Reading: the refusal comes from a combination. The new account uses the manager's email (contradiction b), asks for access to an email system, and the prompt says to hide the inconsistency. Together these read as covert account takeover. No single instruction triggers it on its own.
