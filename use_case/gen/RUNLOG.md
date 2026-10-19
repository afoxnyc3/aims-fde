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
- **Decision (2026-10-18):** the cell is left dead, with the cause recorded above. Running the frontier model first showed one of its limits as a synthetic-data generator: its safety classifier refuses a realistic ticket shape. Next runs move to local models, where temperature and top-p can be set.

## 2026-10-18 — local trial, `qwen3:4b`, base setting (`sweep_qwen3-4b_base_20261018_235625`)

First run of `sweep.py`: local model through LiteLLM → Ollama 0.40.6, with temperature and top-p applied.

- **Slice:** 24 rows, one per cell: `venue_dependent` × `new_hire` (12) and `outside_standard` × `new_hire` (12). Seed 42 for picks. Per-row sampling seed is derived from `row_id`, so it is the same across settings and models.
- **Model:** `ollama_chat/qwen3:4b`, digest `359d7dd4bcda`. `git 791f524`.
- **Settings:** temperature 0.7, top-p 0.8 (Qwen3 model card, non-thinking mode: *looked up*). `top_k` 0, `repeat_penalty` 1.0, `num_ctx` 8192, `think` false. LiteLLM's request body to Ollama was inspected: all six options arrive in `options`, and `think` arrives top-level. top-k 0 = no limit relies on llama.cpp semantics (`ollama ps` shows the llamacpp runner).
- **Result:** 24 generated, 0 unparseable, 0 schema-invalid, 24 schema-valid, **23 verified**, 1 dead cell. After dedupe 23, by construction (one row per cell per setting). Highest cross-cell similarity 0.61 (masked text); none at or above 0.85.
- **Dead cell:** `venue_dependent|new_hire|internal_contradiction|beyond_template`. The model put the requester sign-off in a comment instead of the notes, so verification failed on `names` and `changed` (unexpected comment). This is a real generation miss.
- **Echo (prompt wording copied into the ticket):** 4 rows, all `beyond_template`, with "no other club(s)" taken from the prompt's "Mention no other club." **3 of the 4 passed verification.** Verification proves a ticket contains its picks, not that it reads as plausible. The echo check (`echo_ngrams`) was tuned on this file: it flags exactly these 4 rows and nothing else. Exclusions: code-picked values masked (label fields such as `changed.detail` are not treated as values), mandated phrases masked, stopword-only 3-grams dropped, crude plural fold. It may need retuning when it meets other settings.
- **Timing (*measured*, run alone):** warm-up 5.5 s; median 5.7 s per ticket (range 5.3–7.1); 152 s wall-clock for 24 rows.
- **Failure paths:** `sweep.py --selftest` feeds `classify()` a non-JSON reply and a dict missing required fields. It asserts `unparseable` and `schema_invalid`, and that both records serialize. Passes. No model call.

## Fifty-row read checklist (additions)

Beyond the datasheet's leakage boxes, look for:
- [ ] **Prompt-wording echo:** instruction text copied into notes or comments ("no other club", "use those words", "exactly"). The `echo` flag catches the known pattern, not every phrasing.
- [ ] **Sign-off placement:** the requester's sign-off in the notes, not in a comment.
- [ ] **Fields the picks don't call for:** for example `trainer_level` or `specialties` filled for non-trainer roles (seen on an Aquatics Lead in the 4B smoke test). `verify.py` does not check these.

## 2026-10-19 — fixed rows regenerated with code-picked employee names (`synth_run_20261019_001640`)

- **Why:** in the 126-row run, fixed rows code-picked only the requester, so the model invented the employee. Row `fixed|5` (promotion via general request) came back as "Priya Lindqvist". The name is fictional, but Priya is also the course notebooks' persona.
- **Change:** `picks.py` now code-picks an employee name and email for the fixed rows that concern someone other than the requester (`permission_change`, `offboarding`, `promotion_general`). `generate.py` passes the name in, and `verify.py` checks the employee is named in the summary or notes. Added a `--fixed-only` filter.
- **Side effect:** names come from one seeded rotation, so requester names for fixed rows 2–6 shifted. The 120 crossed rows are unchanged, and the plan still asserts 126 rows with the 36/49/36/5 mix. Fixed-row tickets in earlier run files no longer match the current picks; each stored row keeps the picks it was generated from.
- **Re-pick:** `fixed|5` employee is now Vesper Yarrowby (requester Tobias Copperfield).
- **Result:** 6 planned, 6 generated, 6 schema-valid, **6 verified**. Model `claude-opus-5-5`; temperature not applied.
- **Use:** `use_case/data/review_20.md` takes its two fixed rows (#5 and #6) from this file and all other rows from `synth_run_20261018_221844`.
