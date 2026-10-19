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
